"""Checkpoint management for trained models."""

import os
from pathlib import Path
from typing import List, Optional, Dict, Any
import json


class CheckpointManager:
    """Manages model checkpoints during training."""
    
    def __init__(self, checkpoint_dir: str):
        """
        Initialize checkpoint manager.
        
        Args:
            checkpoint_dir: Directory to store checkpoints
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        print(f"[CheckpointManager] Checkpoint directory: {self.checkpoint_dir}")
    
    def list_checkpoints(self) -> List[str]:
        """
        List all available checkpoints.
        
        Returns:
            List of checkpoint paths
        """
        if not self.checkpoint_dir.exists():
            return []
        
        checkpoints = []
        for item in self.checkpoint_dir.glob("**/pytorch_model.bin"):
            checkpoints.append(str(item.parent))
        
        # Also look for step directories
        for item in self.checkpoint_dir.glob("global_step_*"):
            if item.is_dir():
                checkpoints.append(str(item))
        
        checkpoints.sort()
        return checkpoints
    
    def get_latest_checkpoint(self) -> Optional[str]:
        """
        Get the latest checkpoint path.
        
        Returns:
            Path to latest checkpoint, or None if no checkpoints exist
        """
        checkpoints = self.list_checkpoints()
        if not checkpoints:
            return None
        
        # Try to parse step numbers and get the highest
        step_checkpoints = []
        for ckpt in checkpoints:
            if "global_step_" in ckpt:
                try:
                    step_num = int(ckpt.split("global_step_")[-1].split("/")[0])
                    step_checkpoints.append((step_num, ckpt))
                except:
                    pass
        
        if step_checkpoints:
            step_checkpoints.sort(key=lambda x: x[0], reverse=True)
            return step_checkpoints[0][1]
        
        return checkpoints[-1]
    
    def save_metadata(self, checkpoint_path: str, metadata: Dict[str, Any]) -> None:
        """
        Save metadata for a checkpoint.
        
        Args:
            checkpoint_path: Path to checkpoint
            metadata: Metadata dictionary
        """
        metadata_file = Path(checkpoint_path) / "metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"[CheckpointManager] Saved metadata to {metadata_file}")
    
    def load_metadata(self, checkpoint_path: str) -> Optional[Dict[str, Any]]:
        """
        Load metadata for a checkpoint.
        
        Args:
            checkpoint_path: Path to checkpoint
            
        Returns:
            Metadata dictionary, or None if not found
        """
        metadata_file = Path(checkpoint_path) / "metadata.json"
        if not metadata_file.exists():
            return None
        
        with open(metadata_file, 'r') as f:
            return json.load(f)
    
    def get_checkpoint_info(self, checkpoint_path: str) -> Dict[str, Any]:
        """
        Get information about a checkpoint.
        
        Args:
            checkpoint_path: Path to checkpoint
            
        Returns:
            Dictionary with checkpoint information
        """
        ckpt_path = Path(checkpoint_path)
        
        info = {
            'path': str(ckpt_path),
            'exists': ckpt_path.exists(),
            'size_mb': 0,
            'metadata': None
        }
        
        if ckpt_path.exists():
            # Calculate total size
            total_size = sum(
                f.stat().st_size 
                for f in ckpt_path.rglob('*') 
                if f.is_file()
            )
            info['size_mb'] = total_size / (1024 * 1024)
            
            # Load metadata
            info['metadata'] = self.load_metadata(checkpoint_path)
        
        return info
