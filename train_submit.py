"""提交百炼 fine-tune 任务 - 上传 jsonl + 创建微调。

流程：
  1. 上传 jsonl 文件（OpenAI 兼容接口）→ 拿 file_id
  2. POST /api/v1/fine-tunes 创建微调任务（带 file_id + base model + 超参）
  3. 输出 job_id 和 finetuned_output model name

用法：
  python train_submit.py train_data.jsonl
  python train_submit.py train_data.jsonl --model qwen-max --epochs 3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import SETTINGS
from logger import log


def upload_jsonl(client, jsonl_path: Path) -> str:
    """上传 jsonl 到百炼文件服务，返回 file_id。"""
    print(f"上传文件 {jsonl_path} ...")
    with jsonl_path.open("rb") as f:
        uploaded = client.files.create(file=f, purpose="fine-tune")
    fid = uploaded.id if hasattr(uploaded, "id") else uploaded["id"]
    print(f"  ✅ uploaded file_id={fid}")
    return fid


def create_finetune(api_key: str, file_id: str, model: str, epochs: int, suffix: str):
    """创建 SFT 微调任务（LoRA efficient）。"""
    import requests

    url = "https://dashscope.aliyuncs.com/api/v1/fine-tunes"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "training_datasets": [
            {"data_source_type": "file_id", "file_id": file_id}
        ],
        "hyper_parameters": {
            "n_epochs": epochs,
            "learning_rate": "2e-5",
            "batch_size": 1,
            "save_strategy": "epoch",
            "save_total_limit": 1,
        },
        "training_type": "efficient_sft",  # LoRA
        "finetuned_output_suffix": suffix,
    }
    if not suffix:
        payload.pop("finetuned_output_suffix")

    print("提交 fine-tune 任务 ...")
    print(f"  base model   : {model}")
    print(f"  epochs       : {epochs}")
    print(f"  output suffix: {suffix or '(auto)'}")

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 300:
        print(f"  ❌ HTTP {resp.status_code}: {resp.text[:400]}")
        resp.raise_for_status()
    data = resp.json()
    job_id = data.get("output", {}).get("job_id")
    finetuned_model = data.get("output", {}).get("finetuned_output")
    print(f"  ✅ job_id      = {job_id}")
    print(f"  ✅ 输出模型名  = {finetuned_model}")
    print()
    print("【下一步】等任务完成（百炼会异步跑，分钟 ~ 小时级）：")
    print(f"  控制台 → 模型调优 → 找到 job_id={job_id} 看进度")
    print()
    print("完成后把模型名贴回 vision.py / decision.py 即可启用：")
    print(f'  model="{finetuned_model}"')
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", help="train_export.py 输出的 jsonl 路径")
    parser.add_argument("--model", default="qwen-max",
                        help="基座模型（默认 qwen-max）")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--suffix", default="ygo",
                        help="微调输出模型后缀")
    args = parser.parse_args()

    api_key = SETTINGS.dashscope_api_key
    if not api_key:
        print("❌ 没配置 DASHSCOPE_API_KEY")
        sys.exit(1)

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        print(f"❌ {jsonl_path} 不存在，先跑 train_export.py")
        sys.exit(1)

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

    file_id = upload_jsonl(client, jsonl_path)
    time.sleep(0.5)  # 给后端索引时间
    create_finetune(api_key, file_id, args.model, args.epochs, args.suffix)


if __name__ == "__main__":
    main()
