"""PR5 finetune scaffold — restricted exclusion, adapter wiring, dry-run train/export."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
import yaml

from lds_study.config import Settings
from lds_study.data.models import Chunk, SourceRecord
from lds_study.eval.metrics import AggregateMetrics, meets_regression_baselines
from lds_study.finetune.build_dataset import (
    build_sft_dataset,
    filter_sft_chunks,
    generate_pairs,
)
from lds_study.finetune.merge_and_export import merge_and_export, read_ollama_tag
from lds_study.finetune.train_qlora import (
    conversations_to_messages,
    format_chat_text,
    make_formatting_func,
    run_train,
    validate_sft_jsonl,
)
from lds_study.rag.generate import resolve_generator_model_id


def _chunk(
    *,
    cid: str,
    source_id: str,
    redistributable: bool,
    text: str = "sample verse text",
    verse: int = 1,
) -> Chunk:
    return Chunk(
        id=cid,
        text=text,
        source_id=source_id,
        source_type="scripture",
        redistributable=redistributable,
        volume="bofm",
        book="alma",
        chapter=32,
        verse=verse,
        canonical_ref=f"Alma 32:{verse}",
    )


def _source(
    *,
    sid: str,
    redistributable: bool,
    license: str = "public-domain",
) -> SourceRecord:
    return SourceRecord(
        id=sid,
        type="scripture" if redistributable else "talk",
        loader="public_scripture" if redistributable else "user_files",
        path_or_url="x",
        license=license,
        license_url="https://example.invalid/license",
        verified_on="2026-07-20",
        redistributable=redistributable,
    )


def test_restricted_chunks_never_reach_sft_jsonl(tmp_path: Path) -> None:
    """Plan gate: restricted fixture cannot reach sft.jsonl; no override flag."""
    chunks_path = tmp_path / "chunks.jsonl"
    rows = [
        _chunk(cid="ok/1", source_id="nephi-scriptures", redistributable=True, verse=1),
        _chunk(
            cid="byof/1",
            source_id="user-byof",
            redistributable=False,
            text="conference talk excerpt that must not train",
            verse=2,
        ),
    ]
    with chunks_path.open("w", encoding="utf-8") as fh:
        for c in rows:
            fh.write(json.dumps(c.to_json()) + "\n")

    configs = tmp_path / "configs"
    configs.mkdir()
    sources = {
        "sources": [
            {
                "id": "nephi-scriptures",
                "type": "scripture",
                "loader": "public_scripture",
                "path_or_url": "x",
                "license": "public-domain",
                "license_url": "https://example.invalid/pd",
                "verified_on": "2026-07-20",
                "redistributable": True,
            },
            {
                "id": "user-byof",
                "type": "talk",
                "loader": "user_files",
                "path_or_url": "data/raw/user",
                "license": "copyright",
                "license_url": "https://example.invalid/terms",
                "verified_on": "2026-07-20",
                "redistributable": False,
            },
        ]
    }
    (configs / "sources.yaml").write_text(yaml.safe_dump(sources), encoding="utf-8")

    out = tmp_path / "sft.jsonl"
    settings = Settings(root=tmp_path)
    result = build_sft_dataset(
        chunks_path=chunks_path,
        output_path=out,
        sources_path=configs / "sources.yaml",
        max_pairs=20,
        settings=settings,
    )
    assert result.restricted_dropped >= 1
    assert result.pairs_written >= 1
    text = out.read_text(encoding="utf-8")
    assert "conference talk excerpt" not in text
    assert "byof/1" not in text
    assert "user-byof" not in text
    # No allow-restricted API surface on the builder entrypoint.
    sig = inspect.signature(build_sft_dataset)
    assert "allow_restricted" not in sig.parameters
    assert "include_restricted" not in sig.parameters


def test_filter_sft_drops_restricted_unconditionally() -> None:
    chunks = [
        _chunk(cid="a", source_id="pub", redistributable=True),
        _chunk(cid="b", source_id="byof", redistributable=False),
    ]
    sources = [
        _source(sid="pub", redistributable=True),
        _source(sid="byof", redistributable=False),
    ]
    kept, drops = filter_sft_chunks(chunks, sources=sources)
    assert [c.id for c in kept] == ["a"]
    assert drops["restricted_dropped"] == 1


def test_generate_pairs_produces_sharegpt_types() -> None:
    chunks = [
        _chunk(cid="bofm/alma/32/1", source_id="pub", redistributable=True, verse=1),
        _chunk(
            cid="bofm/alma/32/2",
            source_id="pub",
            redistributable=True,
            text="another verse",
            verse=2,
        ),
    ]
    pairs, counts = generate_pairs(chunks, max_pairs=10)
    assert pairs
    assert counts["explain_verse"] >= 1
    assert "conversations" in pairs[0]
    assert pairs[0]["conversations"][0]["from"] == "human"


def test_resolve_generator_model_id_adapter_tag_and_dir(tmp_path: Path) -> None:
    cfg = {"generator": {"id": "qwen2.5:14b", "adapter": None}}
    assert resolve_generator_model_id(cfg) == "qwen2.5:14b"

    cfg["generator"]["adapter"] = "lds-study-adapter"
    assert resolve_generator_model_id(cfg) == "lds-study-adapter"

    adapter_dir = tmp_path / "adapters" / "run1"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "ollama_tag").write_text("my-lora-tag\n", encoding="utf-8")
    cfg["generator"]["adapter"] = str(adapter_dir)
    assert resolve_generator_model_id(cfg, root=tmp_path) == "my-lora-tag"


def test_resolve_generator_model_id_missing_ollama_tag(tmp_path: Path) -> None:
    empty = tmp_path / "empty-adapter"
    empty.mkdir()
    cfg = {"generator": {"id": "qwen2.5:14b", "adapter": str(empty)}}
    with pytest.raises(ValueError, match="ollama_tag"):
        resolve_generator_model_id(cfg, root=tmp_path)


def test_train_dry_run_and_export_dry_run(tmp_path: Path) -> None:
    sft = tmp_path / "sft.jsonl"
    sft.write_text(
        json.dumps(
            {
                "conversations": [
                    {"from": "human", "value": "hi"},
                    {"from": "gpt", "value": "hello [[x]]"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert validate_sft_jsonl(sft) == 1
    out = tmp_path / "adapters" / "lds-qlora"
    run_train(
        data_path=sft,
        output_dir=out,
        base_model="Qwen/Qwen2.5-14B-Instruct",
        max_steps=20,
        dry_run=True,
    )
    assert (out / "train_config.json").is_file()
    merge_and_export(
        adapter_dir=out,
        base_model="Qwen/Qwen2.5-14B-Instruct",
        ollama_tag="lds-study-adapter",
        dry_run=True,
    )
    assert read_ollama_tag(out) == "lds-study-adapter"
    assert (out / "Modelfile").is_file()


def test_meets_regression_baselines() -> None:
    agg = AggregateMetrics(
        model="adapter",
        n_items=10,
        recall_at_k=0.8,
        recall_n=10,
        citation_validity_rate=0.95,
        citation_n=8,
        adversarial_refusal_rate=0.9,
        adversarial_n=12,
    )
    ok, fails = meets_regression_baselines(
        agg,
        {
            "min_recall_at_k": 0.711,
            "min_citation_validity": 0.9,
            "min_adversarial_refusal": 0.825,
        },
    )
    assert ok and not fails

    bad = AggregateMetrics(
        model="adapter",
        n_items=10,
        recall_at_k=0.8,
        recall_n=10,
        citation_validity_rate=0.5,
        citation_n=8,
        adversarial_refusal_rate=0.9,
        adversarial_n=12,
    )
    ok2, fails2 = meets_regression_baselines(
        bad, {"min_citation_validity": 0.9, "min_adversarial_refusal": 0.825}
    )
    assert not ok2
    assert any("citation_validity" in f for f in fails2)


def test_chat_template_formatting_maps_sharegpt_roles() -> None:
    turns = [
        {"from": "human", "value": "Explain Alma 32:21"},
        {"from": "gpt", "value": "Faith is not a perfect knowledge [[id]]"},
    ]
    messages = conversations_to_messages(turns)
    assert messages == [
        {"role": "user", "content": "Explain Alma 32:21"},
        {"role": "assistant", "content": "Faith is not a perfect knowledge [[id]]"},
    ]

    class _Tok:
        def apply_chat_template(self, msgs, tokenize=False, add_generation_prompt=False):
            assert tokenize is False
            assert add_generation_prompt is False
            return "<|im_start|>" + msgs[0]["role"] + "\n" + msgs[0]["content"]

    text = format_chat_text(_Tok(), messages)
    assert "<|im_start|>user" in text
    assert "human:" not in text

    fmt = make_formatting_func(_Tok())
    out = fmt({"conversations": [turns]})
    assert len(out) == 1
    assert "human:" not in out[0]


def test_build_dataset_sig_has_no_restricted_override() -> None:
    from lds_study.finetune import build_dataset as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert 'add_argument(\n        "--allow-restricted"' not in src
    assert "allow_restricted=" not in src
    assert "dest=\"allow_restricted\"" not in src
    # Docstring may mention the forbidden flag by name; argparse must not expose it.
    assert "parser.add_argument" in src
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("parser.add_argument") or '"--' in stripped:
            assert "allow-restricted" not in stripped
            assert "include-restricted" not in stripped
