"""LoRA model loading utilities."""

from pathlib import Path
from typing import Optional, Dict, Any

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel, PeftConfig
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("[LoRALoader] Warning: PyTorch/Transformers/PEFT not available")


class LoRALoader:
    """Loads base models and applies LoRA weights."""
    
    def __init__(self, base_model_path: str, device: str = "cuda"):
        """
        Initialize LoRA loader.
        
        Args:
            base_model_path: Path to base LLM model
            device: Device to load model on (cuda/cpu)
        """
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch, Transformers, and PEFT are required for LoRA loading")
        
        self.base_model_path = base_model_path
        self.device = device
        self.base_model = None
        self.tokenizer = None
        
        print(f"[LoRALoader] Base model: {base_model_path}")
        print(f"[LoRALoader] Device: {device}")
    
    def load_base_model(self) -> None:
        """Load the base model and tokenizer."""
        if self.base_model is not None:
            print("[LoRALoader] Base model already loaded")
            return
        
        print(f"[LoRALoader] Loading base model from {self.base_model_path}...")
        
        self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_path)
        self.base_model = AutoModelForCausalLM.from_pretrained(
            self.base_model_path,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            device_map=self.device
        )
        
        print("[LoRALoader] Base model loaded successfully")
    
    def load_lora_model(self, lora_checkpoint_path: str):
        """
        Load base model with LoRA weights applied.
        
        Args:
            lora_checkpoint_path: Path to LoRA checkpoint
            
        Returns:
            Tuple of (model, tokenizer)
        """
        # Load base model if not already loaded
        if self.base_model is None:
            self.load_base_model()
        
        print(f"[LoRALoader] Applying LoRA weights from {lora_checkpoint_path}...")
        
        # Load LoRA weights
        model = PeftModel.from_pretrained(
            self.base_model,
            lora_checkpoint_path,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
        )
        
        # Merge weights for inference (optional, faster)
        model = model.merge_and_unload()
        
        print("[LoRALoader] LoRA weights applied successfully")
        
        return model, self.tokenizer
    
    def load_for_inference(self, lora_checkpoint_path: str):
        """
        Load model for inference with LoRA weights.
        
        Args:
            lora_checkpoint_path: Path to LoRA checkpoint
            
        Returns:
            Tuple of (model, tokenizer) ready for inference
        """
        model, tokenizer = self.load_lora_model(lora_checkpoint_path)
        model.eval()  # Set to evaluation mode
        
        print("[LoRALoader] Model ready for inference")
        return model, tokenizer
    
    @staticmethod
    def get_lora_config(lora_checkpoint_path: str) -> Optional[Dict[str, Any]]:
        """
        Get LoRA configuration from checkpoint.
        
        Args:
            lora_checkpoint_path: Path to LoRA checkpoint
            
        Returns:
            LoRA config dictionary
        """
        if not TORCH_AVAILABLE:
            return None
        
        try:
            config = PeftConfig.from_pretrained(lora_checkpoint_path)
            return {
                'base_model': config.base_model_name_or_path,
                'task_type': config.task_type,
                'lora_alpha': config.lora_alpha if hasattr(config, 'lora_alpha') else None,
                'lora_r': config.r if hasattr(config, 'r') else None,
                'lora_dropout': config.lora_dropout if hasattr(config, 'lora_dropout') else None,
            }
        except Exception as e:
            print(f"[LoRALoader] Error loading config: {e}")
            return None


def load_trained_model(
    base_model_path: str,
    checkpoint_path: str,
    device: str = "cuda"
):
    """
    Convenience function to load a trained LoRA model.
    
    Args:
        base_model_path: Path to base LLM
        checkpoint_path: Path to LoRA checkpoint
        device: Device to load on
        
    Returns:
        Tuple of (model, tokenizer)
    """
    loader = LoRALoader(base_model_path, device)
    return loader.load_for_inference(checkpoint_path)
