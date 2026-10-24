# Embedding 模型目录（体积较大，默认不提交权重到 Git）

# 当前使用：bge-small-zh-v1.5/
# 完整目录应包含：
#   model.safetensors / config.json / tokenizer.json / vocab.txt ...
#
# 若目录缺失，可从本机 HF 缓存复制：
#   %USERPROFILE%\.cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5\snapshots\<hash>\
# 复制到：
#   models/bge-small-zh-v1.5/
#
# 然后确认 .env：
#   EMBEDDING_MODEL_PATH=models/bge-small-zh-v1.5

# 可选：bge-reranker-base/（交叉编码器重排，约 1GB）
#   python scripts/download_reranker.py
#   RERANKER_MODEL_PATH=models/bge-reranker-base
# 目录不存在时，检索会自动降级为 BM25 + 向量 RRF，不阻断启动。
