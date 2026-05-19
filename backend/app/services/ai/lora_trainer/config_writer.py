"""
config_writer — generates kohya_ss TOML config from a TrainingJob.
"""
from __future__ import annotations

from pathlib import Path

import toml  # added to requirements.txt


def write_config(
    *,
    dataset_dir: Path,
    output_dir: Path,
    output_name: str,
    base_checkpoint: str,
    trigger_word: str,
    lora_rank: int = 32,
    learning_rate: float = 1e-4,
    epochs: int = 10,
    resolution: int = 1024,
    batch_size: int = 1,
) -> Path:
    """Write a kohya_ss TOML config file; returns the path to the written file."""

    repeat = max(1, 200 // max(1, len(list(dataset_dir.glob("*.png")) + list(dataset_dir.glob("*.jpg")))))

    config = {
        "general": {
            "enable_bucket": True,
        },
        "datasets": [
            {
                "resolution": resolution,
                "batch_size": batch_size,
                "subsets": [
                    {
                        "image_dir": str(dataset_dir),
                        "class_tokens": trigger_word,
                        "num_repeats": repeat,
                    }
                ],
            }
        ],
        "model_arguments": {
            "pretrained_model_name_or_path": base_checkpoint,
            "v2": False,
        },
        "optimizer_arguments": {
            "learning_rate": learning_rate,
            "lr_scheduler": "cosine_with_restarts",
            "lr_warmup_steps": 10,
            "optimizer_type": "AdamW8bit",
        },
        "training_arguments": {
            "max_train_epochs": epochs,
            "save_every_n_epochs": max(1, epochs // 2),
            "mixed_precision": "bf16",
            "gradient_checkpointing": True,
            "xformers": False,
        },
        "network_arguments": {
            "network_module": "networks.lora",
            "network_dim": lora_rank,
            "network_alpha": lora_rank // 2,
        },
        "saving_arguments": {
            "output_dir": str(output_dir),
            "output_name": output_name,
            "save_model_as": "safetensors",
        },
        "sample_prompt_arguments": {
            "sample_every_n_epochs": max(1, epochs // 2),
        },
    }

    config_path = output_dir / "train_config.toml"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        toml.dump(config, f)

    return config_path
