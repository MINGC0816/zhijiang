#!/usr/bin/env python
"""黄金集检索评测。

对比仅向量 / BM25+向量 / 混合+Rerank 的 Recall@K 与上下文支持率
（must_contain 是否出现在 Top-K 切片中，作为忠实度的检索侧代理）。

默认把 samples/ 示例制度入库到独立集合 eval_golden，不污染业务知识库。

用法（在 enterprise_kb_agent 目录）：
  python scripts/eval_retrieval.py
  python scripts/eval_retrieval.py --k 5
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import DATA_DIR, SAMPLES_DIR
from src.ingest.loaders import SUPPORTED_SUFFIXES, load_file
from src.kb.registry import delete_chroma_collection
from src.rag.hybrid import invalidate_lexical_index
from src.rag.rerank import reranker_ready
from src.rag.retriever import retrieve
from src.rag.store import add_documents, get_vectorstore

EVAL_COLLECTION = "eval_golden"
GOLDEN_PATH = _ROOT / "evals" / "golden_set.json"
DISTRACTOR_DIR = _ROOT / "evals" / "distractors"


def _hit_source(doc) -> str:
    return str((doc.metadata or {}).get("source") or "")


def source_recall(docs, expected: list[str]) -> int:
    names = {_hit_source(d) for d in docs}
    return int(any(src in names for src in expected))


def support_rate(docs, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    text = "\n".join(d.page_content or "" for d in docs)
    hit = sum(1 for kw in keywords if kw and kw in text)
    return hit / len(keywords)


def _iter_eval_files() -> list[Path]:
    dirs = [SAMPLES_DIR, DISTRACTOR_DIR]
    paths: list[Path] = []
    for folder in dirs:
        if not folder.is_dir():
            continue
        paths.extend(
            sorted(
                p
                for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
            )
        )
    return paths


def ensure_eval_corpus() -> int:
    """细粒度分块 + 干扰文档，避免「每篇 1 切片」导致 Recall 恒为 100%。"""
    paths = _iter_eval_files()
    if not paths:
        raise SystemExit(f"没有评测语料: {SAMPLES_DIR} / {DISTRACTOR_DIR}")

    delete_chroma_collection(EVAL_COLLECTION)
    get_vectorstore.cache_clear()
    invalidate_lexical_index(EVAL_COLLECTION)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=160,
        chunk_overlap=30,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )
    total_chunks = 0
    ingested: list[str] = []
    for path in paths:
        docs = load_file(path)
        chunks = splitter.split_documents(docs)
        for i, chunk in enumerate(chunks):
            chunk.metadata["source"] = path.name
            chunk.metadata["chunk_id"] = i
        add_documents(chunks, collection_name=EVAL_COLLECTION)
        total_chunks += len(chunks)
        ingested.append(f"{path.name}({len(chunks)})")

    invalidate_lexical_index(EVAL_COLLECTION)
    print(
        f"[OK] eval corpus collection={EVAL_COLLECTION} "
        f"files={ingested} chunks={total_chunks}"
    )
    return total_chunks


def evaluate(items: list[dict], *, k: int, modes: list[str]) -> dict:
    cutoffs = sorted({1, 3, k})
    per_mode: dict[str, dict] = {}
    misses: dict[str, list[str]] = defaultdict(list)
    for mode in modes:
        rec_at = {c: 0 for c in cutoffs}
        support_sum = 0.0
        for item in items:
            hits = retrieve(
                item["question"],
                k=k,
                collection_name=EVAL_COLLECTION,
                mode=mode,
            )
            docs = [h.doc for h in hits]
            expected = item.get("expected_sources") or []
            for c in cutoffs:
                rec_at[c] += source_recall(docs[:c], expected)
            support_sum += support_rate(docs, item.get("must_contain") or [])
            if not source_recall(docs, expected):
                misses[mode].append(item["id"])
        n = len(items) or 1
        per_mode[mode] = {
            "n": len(items),
            "recall_at_k": rec_at[k] / n,
            "recall_at_1": rec_at[1] / n,
            "recall_at_3": rec_at.get(3, rec_at[k]) / n,
            "support_at_k": support_sum / n,
            "missed_ids": misses[mode],
        }
    return {"k": k, "modes": per_mode, "reranker_ready": reranker_ready()}


def print_table(report: dict) -> None:
    k = report["k"]
    print()
    print(
        f"{'mode':<16} {'R@1':<10} {'R@3':<10} {'R@'+str(k):<10} "
        f"{'Support@'+str(k):<12} missed"
    )
    print("-" * 68)
    labels = {
        "vector": "vector",
        "hybrid": "hybrid",
        "hybrid_rerank": "hybrid+rerank",
    }
    for mode, row in report["modes"].items():
        print(
            f"{labels.get(mode, mode):<16} "
            f"{row['recall_at_1']*100:>5.1f}%    "
            f"{row['recall_at_3']*100:>5.1f}%    "
            f"{row['recall_at_k']*100:>5.1f}%    "
            f"{row['support_at_k']*100:>6.1f}%     "
            f"{len(row['missed_ids'])}"
        )
    print()
    if not report["reranker_ready"]:
        print(
            "[NOTE] 未加载 bge-reranker。将 models/bge-reranker-base 放好后，"
            "hybrid+rerank 一列才会出现。下载：python scripts/download_reranker.py"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="黄金集检索评测")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    parser.add_argument("--skip-ingest", action="store_true")
    args = parser.parse_args()

    items = json.loads(args.golden.read_text(encoding="utf-8"))
    if not args.skip_ingest:
        ensure_eval_corpus()

    modes = ["vector", "hybrid"]
    if reranker_ready():
        modes.append("hybrid_rerank")

    report = evaluate(items, k=max(1, args.k), modes=modes)
    print_table(report)

    out_dir = DATA_DIR / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "last_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] report written to {out_path}")

    vector = report["modes"].get("vector", {})
    best_name = "hybrid_rerank" if "hybrid_rerank" in report["modes"] else "hybrid"
    best = report["modes"][best_name]
    print(
        f"[RESUME] Recall@1：{best_name} {best['recall_at_1']*100:.1f}%  vs  "
        f"vector {vector.get('recall_at_1', 0)*100:.1f}% ；"
        f"Recall@{report['k']}：{best['recall_at_k']*100:.1f}% vs "
        f"{vector.get('recall_at_k', 0)*100:.1f}%"
    )


if __name__ == "__main__":
    main()
