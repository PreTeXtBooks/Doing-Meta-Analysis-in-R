#!/usr/bin/env python3
"""
Copy and convert images to PreTeXt generated-assets directory.
This script prepares images for the PreTeXt build process.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

def main():
    # Define paths
    script_dir = Path(__file__).parent
    source_images_dir = script_dir / "images"
    source_figs_dir = script_dir / "_figs"
    source_ptx_dir = script_dir / "pretext" / "source"
    # Put generated images in pretext/assets/generated/ directory
    # This matches the publication.ptx configuration where "external" is ../assets
    # and source files reference images as source="generated/*.png"
    pretext_assets = script_dir / "pretext" / "assets" / "generated"
    pretext_fig_assets = script_dir / "pretext" / "assets" / "_figs"
    
    print("Preparing images for PreTeXt book...")
    print(f"Source: {source_images_dir}")
    print(f"Source _figs: {source_figs_dir}")
    print(f"Target: {pretext_assets}")
    print(f"Target _figs: {pretext_fig_assets}")
    
    # Create assets/generated directory
    pretext_assets.mkdir(parents=True, exist_ok=True)
    pretext_fig_assets.mkdir(parents=True, exist_ok=True)
    
    # Check if ImageMagick convert is available
    convert_available = shutil.which("convert") is not None
    
    if convert_available:
        print("ImageMagick found - will convert EPS to PNG")
    else:
        print("ImageMagick not found - will only copy existing PNG files")
    
    images_copied = 0
    images_converted = 0
    figs_copied = 0
    
    # Copy existing PNG files first
    for png_file in source_images_dir.rglob("*.png"):
        # Skip defunct images
        if "defunct_images" in str(png_file):
            continue
            
        target_file = pretext_assets / png_file.name
        shutil.copy2(png_file, target_file)
        images_copied += 1
        print(f"  Copied: {png_file.name}")
    
    # Convert EPS files to PNG if ImageMagick is available
    if convert_available:
        for eps_file in source_images_dir.rglob("*.eps"):
            # Get the base filename without extension
            base_name = eps_file.stem
            target_file = pretext_assets / f"{base_name}.png"
            
            # Skip if PNG already exists
            if target_file.exists():
                continue
            
            try:
                # Convert EPS to PNG using ImageMagick
                subprocess.run([
                    "convert",
                    "-density", "300",
                    "-quality", "90",
                    str(eps_file),
                    str(target_file)
                ], check=True, capture_output=True, text=True)
                
                images_converted += 1
                print(f"  Converted: {base_name}.eps -> {base_name}.png")
            except subprocess.CalledProcessError as e:
                print(f"  Warning: Failed to convert {eps_file.name}: {e}")
                continue
            except Exception as e:
                print(f"  Warning: Error processing {eps_file.name}: {e}")
                continue

    # Copy all chapter opener images referenced as source="_figs/<name>"
    # to pretext/assets/_figs so they render in PreTeXt output.
    fig_references = set()
    fig_pattern = re.compile(r'<image\s+source="_figs/([^"]+)"')
    for ptx_file in source_ptx_dir.glob("*.ptx"):
        text = ptx_file.read_text(encoding="utf-8")
        fig_references.update(fig_pattern.findall(text))

    for fig_name in sorted(fig_references):
        source_path = source_images_dir / fig_name
        if not source_path.exists():
            source_path = source_figs_dir / fig_name

        if not source_path.exists():
            print(f"  Warning: Missing referenced _figs image: {fig_name}")
            continue

        shutil.copy2(source_path, pretext_fig_assets / fig_name)
        figs_copied += 1
        print(f"  Copied _figs image: {fig_name}")
    
    # Summary
    total_images = len(list(pretext_assets.glob("*.png")))
    print(f"\nComplete!")
    print(f"  Copied: {images_copied} PNG files")
    print(f"  Converted: {images_converted} EPS files")
    print(f"  Copied _figs images: {figs_copied}")
    print(f"  Total images in assets/generated: {total_images}")
    
    if total_images == 0:
        print("\nNote: No images were found in the source directory.")

    return 0

if __name__ == "__main__":
    exit(main())
