import os
import sys
import struct
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import shutil
import tempfile
import subprocess
import threading
import json
import glob
import time
import hashlib
import ctypes
import zipfile
import urllib.request
from pathlib import Path

try:
    from PIL import Image, ImageTk, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

if not HAS_PIL:
    root = tk.Tk()
    root.withdraw()
    result = messagebox.askyesno("Missing Dependencies", 
                                "Pillow library is required but not installed.\n\nWould you like to install it now?")
    if result:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
            messagebox.showinfo("Success", "Pillow installed successfully. Please restart the application.")
        except:
            messagebox.showerror("Error", "Failed to install Pillow. Please install it manually: pip install Pillow")
        sys.exit(1)
    sys.exit(1)

CONFIG_FILE = "config.json"
CACHE_DIR = "texture_cache"
DECODE_CACHE = {}

class ADBPlatformTools:
    """ADB Platform Tools installation and management"""
    
    @staticmethod
    def get_safe_install_directory():
        """Get a directory where we have write permissions"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        install_dir = os.path.join(script_dir, "platform-tools")
        return install_dir

    @staticmethod
    def install_platform_tools():
        """Download and install Android Platform Tools to a safe location"""
        import platform
        system = platform.system().lower()
        
        download_urls = {
            'windows': 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip',
            'linux': 'https://dl.google.com/android/repository/platform-tools-latest-linux.zip', 
            'darwin': 'https://dl.google.com/android/repository/platform-tools-latest-darwin.zip'
        }
        
        url = download_urls.get(system)
        if not url:
            return False, f"Unsupported platform: {system}"
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        install_base = os.path.join(script_dir, "platform-tools")
        download_path = os.path.join(script_dir, "platform-tools-download.zip")
        
        try:
            os.makedirs(install_base, exist_ok=True)
            
            def download_progress(count, block_size, total_size):
                percent = int(count * block_size * 100 / total_size)
                print(f"Downloading: {percent}%")
            
            print(f"Downloading Platform Tools to: {download_path}")
            urllib.request.urlretrieve(url, download_path, download_progress)
            
            print(f"Extracting to: {install_base}")
            with zipfile.ZipFile(download_path, 'r') as zip_ref:
                zip_ref.extractall(install_base)
            
            try:
                os.remove(download_path)
            except:
                pass
            
            adb_path = os.path.join(install_base, "platform-tools", "adb.exe" if system == 'windows' else "adb")
            if not os.path.exists(adb_path):
                adb_path = os.path.join(install_base, "adb.exe" if system == 'windows' else "adb")
            
            if os.path.exists(adb_path):
                if system != 'windows':
                    try:
                        os.chmod(adb_path, 0o755)
                    except:
                        pass

                adb_dir = os.path.dirname(adb_path)
                os.environ['PATH'] = adb_dir + os.pathsep + os.environ['PATH']
                
                return True, f"Platform Tools installed to: {adb_dir}"
            else:
                return False, "ADB executable not found after extraction"
                
        except Exception as e:
            return False, f"Installation failed: {str(e)}"

class ADBManager:
    """Complete ADB management"""
    
    @staticmethod
    def find_adb():
        """Find ADB in safe install location or PATH"""
        safe_dir = ADBPlatformTools.get_safe_install_directory()
        local_paths = [
            os.path.join(safe_dir, "platform-tools", "adb.exe"),
            os.path.join(safe_dir, "platform-tools", "adb"),
            os.path.join(safe_dir, "adb.exe"), 
            os.path.join(safe_dir, "adb")
        ]
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        local_paths.extend([
            os.path.join(script_dir, "platform-tools", "adb.exe"),
            os.path.join(script_dir, "platform-tools", "adb"),
            os.path.join(script_dir, "adb.exe"),
            os.path.join(script_dir, "adb")
        ])
        
        for path in local_paths:
            if os.path.exists(path):
                return path
        
        try:
            result = subprocess.run(['adb', 'version'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return 'adb'
        except:
            pass
            
        return None

    @staticmethod
    def check_adb():
        """Check ADB and device connection"""
        adb_path = ADBManager.find_adb()
        if not adb_path:
            return False, "ADB not found", None
        
        try:
            try:
                subprocess.run([adb_path, 'kill-server'], capture_output=True, timeout=5)
            except:
                pass
            
            result = subprocess.run([adb_path, 'devices'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = [line for line in result.stdout.strip().split('\n') if '\tdevice' in line]
                if lines:
                    devices = []
                    for line in lines:
                        device_id = line.split('\t')[0]
                        info_result = subprocess.run([adb_path, '-s', device_id, 'shell', 'getprop', 'ro.product.model'], 
                                                   capture_output=True, text=True, timeout=10)
                        model = info_result.stdout.strip() if info_result.returncode == 0 else "Unknown"
                        devices.append(f"{device_id} ({model})")
                    
                    return True, f"Connected: {', '.join(devices)}", adb_path
                else:
                    return True, "No devices connected", adb_path
            return False, "ADB command failed", adb_path
        except subprocess.TimeoutExpired:
            return False, "ADB timeout", adb_path
        except Exception as e:
            return False, f"ADB error: {str(e)}", adb_path

    @staticmethod
    def push_to_quest(local_folder, quest_path):
        """Push files to Quest - pushes contents of folder, not the folder itself"""
        adb_path = ADBManager.find_adb()
        if not adb_path:
            return False, "ADB not available"
        
        try:
            result = subprocess.run([adb_path, 'shell', 'mkdir', '-p', quest_path], 
                                  capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return False, f"Failed to create directory: {result.stderr}"
            
            success_count = 0
            total_count = 0
            errors = []
            
            for item in os.listdir(local_folder):
                item_path = os.path.join(local_folder, item)
                if os.path.exists(item_path):
                    total_count += 1
                    print(f"Pushing: {item}")
                    
                    result = subprocess.run([adb_path, 'push', item_path, quest_path], 
                                          capture_output=True, text=True, timeout=60)
                    
                    if result.returncode == 0:
                        success_count += 1
                        print(f"✅ Successfully pushed: {item}")
                    else:
                        error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                        errors.append(f"{item}: {error_msg}")
                        print(f"❌ Failed to push {item}: {error_msg}")
            
            if success_count == total_count:
                return True, f"Successfully pushed all {success_count} items to {quest_path}"
            elif success_count > 0:
                return True, f"Partially successful: {success_count}/{total_count} items pushed to {quest_path}. Errors: {', '.join(errors)}"
            else:
                return False, f"Failed to push any items. Errors: {', '.join(errors)}"
                    
        except subprocess.TimeoutExpired:
            return False, "Push operation timed out"
        except Exception as push_error:
            return False, f"Push error: {str(push_error)}"

    @staticmethod
    def install_adb_tools():
        """Install ADB tools"""
        return ADBPlatformTools.install_platform_tools()

class ASTCTools:
    """ASTC encoding/decoding for Quest textures"""
    
    @staticmethod
    def load_texture_mapping(mapping_file):
        """Load texture resolutions from mapping file"""
        if not mapping_file.exists():
            return {}
        
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            return mapping
        except Exception as e:
            print(f"Mapping load error: {e}")
            return {}

    @staticmethod
    def find_texture_info(texture_name, mapping):
        """Find texture info in mapping"""
        if texture_name in mapping:
            return mapping[texture_name]
        
        suffixes = ['_d', '_n', '_s', '_e', '_a', '_r', '_m', '_h']
        for suffix in suffixes:
            if texture_name.endswith(suffix):
                base_name = texture_name[:-len(suffix)]
                if base_name in mapping:
                    return mapping[base_name]
        
        return None

    @staticmethod
    def wrap_raw_astc(raw_path, wrapped_path, width, height, block_width=4, block_height=4):
        """Add ASTC header to raw data"""
        try:
            magic = struct.pack("<I", 0x5CA1AB13)
            block_dims = struct.pack("3B", block_width, block_height, 1)
            
            def dim3(x):
                return struct.pack("<I", x)[:3]
                
            image_dims = dim3(width) + dim3(height) + dim3(1)
            header = magic + block_dims + image_dims
            data = raw_path.read_bytes()
            wrapped_path.write_bytes(header + data)
            return True
        except Exception as e:
            print(f"Wrap failed: {e}")
            return False

    @staticmethod
    def decode_with_config(astcenc_path, raw_file, output_file, width, height, block_w, block_h, cache_key=None):
        """Try decoding with specific config"""
        temp_astc = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.astc', delete=False) as f:
                temp_astc = Path(f.name)
            
            if not ASTCTools.wrap_raw_astc(raw_file, temp_astc, width, height, block_w, block_h):
                return False
            
            result = subprocess.run([
                str(astcenc_path),
                "-dl",
                str(temp_astc),
                str(output_file)
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and output_file.exists():
                file_size = output_file.stat().st_size
                if file_size > 1000:
                    if cache_key:
                        DECODE_CACHE[cache_key] = {
                            'width': width,
                            'height': height, 
                            'block_w': block_w,
                            'block_h': block_h,
                            'original_size': raw_file.stat().st_size
                        }
                    return True
                else:
                    output_file.unlink()
                    return False
            else:
                if output_file.exists():
                    output_file.unlink()
                return False
                
        except Exception:
            if output_file.exists():
                output_file.unlink()
            return False
        finally:
            if temp_astc and temp_astc.exists():
                try:
                    temp_astc.unlink()
                except:
                    pass

    @staticmethod
    def get_common_block_sizes():
        """Return common ASTC block sizes"""
        return [
            (4, 4), (8, 8), (6, 6), (5, 5), 
            (10, 10), (12, 12), (5, 4), (6, 5),
            (8, 5), (8, 6), (10, 5), (10, 6), (10, 8)
        ]

    @staticmethod
    def decode_with_mapping(astcenc_path, texture_file, output_path, mapping):
        """Decode using texture mapping"""
        texture_name = texture_file.stem
        texture_info = ASTCTools.find_texture_info(texture_name, mapping)
        
        if not texture_info:
            return False
        
        pcvr_width = texture_info['width']
        pcvr_height = texture_info['height']
        
        block_sizes = ASTCTools.get_common_block_sizes()
        
        for block_w, block_h in block_sizes:
            output_file = output_path / f"{texture_file.stem}.png"
            
            if ASTCTools.decode_with_config(astcenc_path, texture_file, output_file, pcvr_width, pcvr_height, block_w, block_h, texture_name):
                return True
        
        return False

    @staticmethod
    def brute_force_decode(astcenc_path, texture_file, output_path):
        """Brute force decode"""
        configurations = [
            (2048, 1024, 8, 8, "2Kx1K_8x8"),
            (2048, 1024, 6, 6, "2Kx1K_6x6"),
            (2048, 1024, 4, 4, "2Kx1K_4x4"),
            (1024, 512, 8, 8, "1Kx512_8x8"),
            (1024, 512, 6, 6, "1Kx512_6x6"),
            (1024, 512, 4, 4, "1Kx512_4x4"),
            (2048, 2048, 8, 8, "2K_square_8x8"),
            (1024, 1024, 8, 8, "1K_square_8x8"),
        ]
        
        file_size = texture_file.stat().st_size
        
        for width, height, block_w, block_h, desc in configurations:
            expected_size = ASTCTools.calculate_astc_size(width, height, block_w, block_h)
            
            if abs(expected_size - file_size) > 100:
                continue
                
            output_file = output_path / f"{texture_file.stem}_BF_{desc}.png"
            
            if ASTCTools.decode_with_config(astcenc_path, texture_file, output_file, width, height, block_w, block_h, texture_file.stem):
                return True
        
        return False

    @staticmethod
    def calculate_astc_size(width, height, block_w, block_h):
        """Calculate expected ASTC file size"""
        blocks_x = (width + block_w - 1) // block_w
        blocks_y = (height + block_h - 1) // block_h
        return blocks_x * blocks_y * 16

    @staticmethod
    def pad_to_size(data, target_size):
        """Pad data to target size"""
        current_size = len(data)
        if current_size < target_size:
            padding = b'\x00' * (target_size - current_size)
            return data + padding
        elif current_size > target_size:
            return data[:target_size]
        else:
            return data

    @staticmethod
    def encode_texture(astcenc_path, input_png, output_file, width, height, block_w, block_h, quality="medium", target_size=None):
        """Encode PNG to ASTC"""
        temp_astc = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.astc', delete=False) as f:
                temp_astc = Path(f.name)
            
            result = subprocess.run([
                str(astcenc_path),
                "-cl",
                str(input_png),
                str(temp_astc),
                f"{block_w}x{block_h}",
                f"-{quality}",
                "-silent"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                return False
            
            with open(temp_astc, 'rb') as f:
                astc_data = f.read()
            
            if len(astc_data) > 16 and astc_data[:4] == b'\x13\xAB\xA1\x5C':
                raw_data = astc_data[16:]
            else:
                raw_data = astc_data
            
            if target_size:
                expected_size = ASTCTools.calculate_astc_size(width, height, block_w, block_h)
                if len(raw_data) != target_size:
                    raw_data = ASTCTools.pad_to_size(raw_data, target_size)
            
            output_file.write_bytes(raw_data)
            return True
            
        except subprocess.TimeoutExpired:
            return False
        except Exception as e:
            return False
        finally:
            if temp_astc and temp_astc.exists():
                temp_astc.unlink(missing_ok=True)

    @staticmethod
    def encode_with_cache(astcenc_path, input_png, output_file, texture_name, quality="medium"):
        """Encode using cached config"""
        if texture_name not in DECODE_CACHE:
            return False
        
        config = DECODE_CACHE[texture_name]
        width = config['width']
        height = config['height']
        block_w = config['block_w']
        block_h = config['block_h']
        target_size = config['original_size']
        
        return ASTCTools.encode_texture(astcenc_path, input_png, output_file, width, height, block_w, block_h, quality, target_size)

    @staticmethod
    def save_decode_cache(cache_file):
        """Save decode cache"""
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(DECODE_CACHE, f, indent=2)
        except Exception as e:
            print(f"Cache save error: {e}")

    @staticmethod
    def load_decode_cache(cache_file):
        """Load decode cache"""
        global DECODE_CACHE
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    DECODE_CACHE = json.load(f)
            except Exception as e:
                print(f"Cache load error: {e}")

class ConfigManager:
    """Configuration management"""
    
    @staticmethod
    def load_config():
        config = {
            'output_folder': None,
            'input_folder': None,
            'renderdoc_path': None,
            'data_folder': None,
            'extracted_folder': None,
            'quest_input_folder': None,
            'repacked_folder': None
        }
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    config.update(loaded_config)
        except Exception as e:
            print(f"Config load error: {e}")
        
        return config
    
    @staticmethod
    def save_config(**kwargs):
        config = ConfigManager.load_config()
        config.update(kwargs)
        
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            print(f"Config save error: {e}")

class EVRToolsManager:
    """EVR file tools management"""
    
    def __init__(self):
        self.tool_path = self.find_tool()
        
    def find_tool(self):
        """Find evrFileTools.exe"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths = [
            os.path.join(script_dir, "evrFileTools.exe"),
            os.path.join(script_dir, "echoModifyFiles.exe"),
            os.path.join(script_dir, "echoFileTools.exe"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    def extract_package(self, data_dir, package_name, output_dir):
        """Extract package"""
        if not self.tool_path:
            return False, "evrFileTools.exe not found"
        
        try:
            cmd = [
                self.tool_path,
                "-mode", "extract",
                "-packageName", package_name,
                "-dataDir", data_dir,
                "-outputDir", output_dir
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  cwd=os.path.dirname(self.tool_path), timeout=2000)
            
            if result.returncode == 0:
                return True, f"Extracted to {output_dir}"
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                return False, f"Extraction failed: {error_msg}"
                
        except subprocess.TimeoutExpired:
            return False, "Extraction timeout"
        except Exception as e:
            return False, f"Extraction error: {str(e)}"
    
    def repack_package(self, output_dir, package_name, data_dir, input_dir):
        """Repack package"""
        if not self.tool_path:
            return False, "evrFileTools.exe not found"
        
        try:
            cmd = [
                self.tool_path,
                "-mode", "replace",
                "-packageName", package_name,
                "-dataDir", data_dir,
                "-inputDir", input_dir,
                "-outputDir", output_dir
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  cwd=os.path.dirname(self.tool_path), timeout=2000)
            
            if result.returncode == 0:
                return True, f"Repacked to {output_dir}"
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                return False, f"Repacking failed: {error_msg}"
                
        except subprocess.TimeoutExpired:
            return False, "Repacking timeout"
        except Exception as e:
            return False, f"Repacking error: {str(e)}"

class DDSHandler:
    """DDS file handling"""
    
    DXGI_FORMAT = {
        0: "DXGI_FORMAT_UNKNOWN",
        71: "DXGI_FORMAT_BC1_UNORM",
        77: "DXGI_FORMAT_BC3_UNORM", 
        80: "DXGI_FORMAT_BC4_UNORM",
        83: "DXGI_FORMAT_BC5_UNORM",
    }
    
    @staticmethod
    def get_dds_info(file_path):
        try:
            with open(file_path, 'rb') as f:
                signature = f.read(4)
                if signature != b'DDS ':
                    return None
                
                header = f.read(124)
                if len(header) < 124:
                    return None
                
                height = struct.unpack('<I', header[8:12])[0]
                width = struct.unpack('<I', header[12:16])[0]
                mipmap_count = struct.unpack('<I', header[24:28])[0]
                
                pixel_format_flags = struct.unpack('<I', header[76:80])[0]
                four_cc = header[80:84]
                
                format_name = "Unknown"
                format_code = None
                is_problematic = False
                
                if four_cc == b'DXT1':
                    format_name = "BC1/DXT1"
                elif four_cc == b'DXT3':
                    format_name = "BC2/DXT3"
                elif four_cc == b'DXT5':
                    format_name = "BC3/DXT5"
                elif four_cc == b'DX10':
                    extended_header = f.read(20)
                    if len(extended_header) >= 20:
                        format_code = struct.unpack('<I', extended_header[0:4])[0]
                        format_name = DDSHandler.DXGI_FORMAT.get(format_code, f"DXGI Format {format_code}")
                        
                        if format_code in [26, 72, 78]:
                            is_problematic = True
                elif pixel_format_flags & 0x40:
                    format_name = "RGB"
                
                return {
                    'width': width,
                    'height': height,
                    'mipmaps': mipmap_count,
                    'format': format_name,
                    'file_size': os.path.getsize(file_path),
                    'format_code': format_code,
                    'is_problematic': is_problematic
                }
                
        except Exception:
            return None
    
    @staticmethod
    def create_format_preview(width, height, format_name, file_path):
        img = Image.new('RGB', (max(256, width), max(256, height)), '#1a1a3a')
        draw = ImageDraw.Draw(img)
        
        grid_size = 32
        for x in range(0, img.width, grid_size):
            draw.line([(x, 0), (x, img.height)], fill='#2a2a5a', width=1)
        for y in range(0, img.height, grid_size):
            draw.line([(0, y), (img.width, y)], fill='#2a2a5a', width=1)
        
        y_pos = 20
        draw.text((20, y_pos), f"Format: {format_name}", fill='#00a8ff')
        y_pos += 25
        draw.text((20, y_pos), f"Size: {width}x{height}", fill='#ffffff')
        y_pos += 25
        draw.text((20, y_pos), f"File: {os.path.basename(file_path)}", fill='#b8b8d9')
        
        return img

class TextureLoader:
    """Texture loading and caching"""
    
    @staticmethod
    def get_cache_path(texture_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cache_dir = os.path.join(script_dir, CACHE_DIR)
        os.makedirs(cache_dir, exist_ok=True)
        
        original_name = os.path.basename(texture_path)
        png_name = os.path.splitext(original_name)[0] + ".png"
        
        return os.path.join(cache_dir, png_name)
    
    @staticmethod
    def is_quest_texture_folder(textures_folder):
        return os.path.basename(textures_folder) == "5231972605540061417"
    
    @staticmethod
    def is_pcvr_texture_folder(textures_folder):
        return os.path.basename(textures_folder) == "-4707359568332879775"
    
    @staticmethod
    def get_astcenc_path():
        script_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths = [
            os.path.join(script_dir, "astcenc-avx2.exe"),
            os.path.join(script_dir, "astcenc.exe"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    @staticmethod
    def load_texture(texture_path, is_quest_texture=False):
        try:
            cache_path = TextureLoader.get_cache_path(texture_path)
            if os.path.exists(cache_path):
                try:
                    img = Image.open(cache_path).convert("RGBA")
                    return img
                except Exception as e:
                    try:
                        os.remove(cache_path)
                    except:
                        pass
            
            if is_quest_texture:
                return TextureLoader.load_quest_texture(texture_path, cache_path)
            else:
                return TextureLoader.load_dds_texture(texture_path, cache_path)

        except Exception as e:
            return DDSHandler.create_format_preview(256, 256, "Error Loading", texture_path)

    @staticmethod
    def load_quest_texture(texture_path, cache_path):
        try:
            astcenc_path = TextureLoader.get_astcenc_path()
            if not astcenc_path:
                return DDSHandler.create_format_preview(256, 256, "Missing astcenc", texture_path)
            
            temp_dir = tempfile.mkdtemp(prefix="astc_decode_")
            temp_output = os.path.join(temp_dir, "decoded.png")
            
            texture_file = Path(texture_path)
            output_path = Path(temp_dir)
            
            script_dir = os.path.dirname(os.path.abspath(__file__))
            mapping_file = Path(script_dir) / "texture_mapping.json"
            mapping = {}
            if mapping_file.exists():
                mapping = ASTCTools.load_texture_mapping(mapping_file)
            
            success = ASTCTools.decode_with_mapping(astcenc_path, texture_file, output_path, mapping)
            if not success:
                success = ASTCTools.brute_force_decode(astcenc_path, texture_file, output_path)
            
            if success:
                png_files = list(output_path.glob("*.png"))
                if png_files:
                    img = Image.open(png_files[0]).convert("RGBA")
                    try:
                        img.save(cache_path)
                    except Exception as e:
                        pass
                    
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return img
            
            shutil.rmtree(temp_dir, ignore_errors=True)
            return DDSHandler.create_format_preview(256, 256, "ASTC Decode Failed", texture_path)
            
        except Exception as e:
            return DDSHandler.create_format_preview(256, 256, "ASTC Error", texture_path)

    @staticmethod
    def load_dds_texture(dds_path, cache_path):
        dds_info = DDSHandler.get_dds_info(dds_path)

        if dds_info and dds_info.get("is_problematic", False):
            return TextureLoader.load_with_texconv(dds_path, cache_path)

        try:
            img = Image.open(dds_path)
            if img:
                try:
                    img.save(cache_path)
                except Exception as e:
                    pass
                return img
        except Exception as e:
            pass

        return TextureLoader.load_with_texconv(dds_path, cache_path)

    @staticmethod
    def load_with_texconv(dds_path, cache_path=None):
        import struct

        temp_input = None
        temp_dir = None

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            texconv_path = os.path.join(script_dir, "texconv.exe")

            if not os.path.exists(texconv_path):
                return DDSHandler.create_format_preview(256, 256, "Missing texconv.exe", dds_path)

            with open(dds_path, "rb") as f:
                raw_data = f.read()

            is_dds = raw_data[:4] == b"DDS "

            temp_input = tempfile.NamedTemporaryFile(suffix=".dds", delete=False)
            temp_input.close()

            if is_dds:
                shutil.copy(dds_path, temp_input.name)
            else:
                dds_info = DDSHandler.get_dds_info(dds_path)
                width = dds_info.get("width", 256)
                height = dds_info.get("height", 256)

                format_code = 71  
                fmt_str = dds_info.get("format", "")

                if "DXGI_FORMAT_BC1" in fmt_str:
                    format_code = 71
                elif "DXGI_FORMAT_BC3" in fmt_str:
                    format_code = 77
                elif "DXGI_FORMAT_BC4" in fmt_str:
                    format_code = 80
                elif "DXGI_FORMAT_BC5" in fmt_str:
                    format_code = 83
                elif "DXGI_FORMAT_R11G11B10_FLOAT" in fmt_str:
                    format_code = 26

                header = b"DDS "                                  
                header += struct.pack("<I", 124)                  
                header += struct.pack("<I", 0x0002100F)           
                header += struct.pack("<I", height)               
                header += struct.pack("<I", width)                
                header += struct.pack("<I", 0)                    
                header += struct.pack("<I", 0)                    
                header += struct.pack("<I", 1)                    
                header += b"\x00" * (11 * 4)                      

                header += struct.pack("<I", 32)                   
                header += struct.pack("<I", 4)                    
                header += b"DX10"                                 
                header += struct.pack("<I", 0)                    
                header += struct.pack("<I", 0)                    
                header += struct.pack("<I", 0)                    
                header += struct.pack("<I", 0)                    
                header += struct.pack("<I", 0)                    

                header += struct.pack("<I", 0x1000)               
                header += struct.pack("<I", 0)                    
                header += struct.pack("<I", 0)                    
                header += struct.pack("<I", 0)                    
                header += struct.pack("<I", 0)                    

                dx10_header = struct.pack("<I", format_code)      
                dx10_header += struct.pack("<I", 3)               
                dx10_header += struct.pack("<I", 0)               
                dx10_header += struct.pack("<I", 1)               
                dx10_header += struct.pack("<I", 0)               

                with open(temp_input.name, "wb") as out:
                    out.write(header)
                    out.write(dx10_header)
                    out.write(raw_data)

            dds_info = DDSHandler.get_dds_info(dds_path)
            force_format = None
            if dds_info and "DXGI_FORMAT_R11G11B10_FLOAT" in dds_info.get("format", ""):
                force_format = "R16G16B16A16_FLOAT"

            temp_dir = tempfile.mkdtemp(prefix="texconv_")
            cmd = [
                texconv_path,
                "-ft", "png",
                "-o", temp_dir,
                "-y"
            ]
            if force_format:
                cmd.extend(["-f", force_format])
            cmd.append(temp_input.name)

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                return DDSHandler.create_format_preview(256, 256, "texconv error", dds_path)

            base = os.path.splitext(os.path.basename(temp_input.name))[0]
            converted_file = os.path.join(temp_dir, base + ".png")
            if os.path.exists(converted_file):
                img = Image.open(converted_file).convert("RGBA")
                
                if cache_path:
                    try:
                        img.save(cache_path)
                    except Exception as e:
                        pass
                
                shutil.rmtree(temp_dir, ignore_errors=True)
                return img
            else:
                return DDSHandler.create_format_preview(256, 256, "texconv failed", dds_path)

        except Exception as e:
            return DDSHandler.create_format_preview(256, 256, "texconv error", dds_path)
        finally:
            if temp_input and os.path.exists(temp_input.name):
                try:
                    os.remove(temp_input.name)
                except Exception:
                    pass
            
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

class TextureCacheManager:
    """Texture filtering using cache.json"""
    
    @staticmethod
    def load_texture_cache(cache_path):
        texture_cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cache_data = json.load(f)
                
                texture_cache = {key: True for key in cache_data.keys()}
            except Exception as e:
                texture_cache = {}
        return texture_cache

class TextureReplacer:
    """Texture replacement functionality"""
    
    @staticmethod
    def hex_edit_file_size(file_path, new_size):
        """Update file size in header"""
        try:
            with open(file_path, 'r+b') as f:
                data = bytearray(f.read())
                
                if len(data) >= 248:
                    file_size_bytes = struct.pack('<I', new_size)
                    data[244:248] = file_size_bytes
                    
                    f.seek(0)
                    f.write(data)
                    f.truncate()
                    
                    return True
                else:
                    return False
                
        except Exception as e:
            return False
    
    @staticmethod
    def replace_pcvr_texture(output_folder, input_folder, original_texture_path, replacement_texture_path, replacement_size):
        try:
            input_textures_folder = os.path.join(input_folder, "0", "-4707359568332879775")
            input_corresponding_folder = os.path.join(input_folder, "0", "5353709876897953952")
            
            os.makedirs(input_textures_folder, exist_ok=True)
            os.makedirs(input_corresponding_folder, exist_ok=True)
            
            texture_name = os.path.basename(original_texture_path)
            output_corresponding_file = os.path.join(output_folder, "5353709876897953952", texture_name)
            
            input_texture_path = os.path.join(input_textures_folder, texture_name)
            input_corresponding_path = os.path.join(input_corresponding_folder, texture_name)
            
            shutil.copy2(replacement_texture_path, input_texture_path)
            
            if os.path.exists(output_corresponding_file):
                shutil.copy2(output_corresponding_file, input_corresponding_path)
                
                success = TextureReplacer.hex_edit_file_size(input_corresponding_path, replacement_size)
                
                if success:
                    return True, f"PCVR texture replaced. Size updated to {replacement_size} bytes."
                else:
                    return False, "Failed to update file size"
            else:
                return False, "Corresponding file not found"
                
        except Exception as e:
            return False, f"PCVR replacement error: {str(e)}"

    @staticmethod
    def replace_quest_texture(output_folder, quest_input_folder, original_texture_path, replacement_texture_path, texture_cache):
        try:
            input_textures_folder = os.path.join(quest_input_folder, "0", "5231972605540061417")
            input_corresponding_folder = os.path.join(quest_input_folder, "0", "-2094201140079393352")
            
            os.makedirs(input_textures_folder, exist_ok=True)
            os.makedirs(input_corresponding_folder, exist_ok=True)
            
            texture_name = os.path.basename(original_texture_path)
            original_size = os.path.getsize(original_texture_path)
            
            astcenc_path = TextureLoader.get_astcenc_path()
            if not astcenc_path:
                return False, "astcenc not found"
            
            script_dir = os.path.dirname(os.path.abspath(__file__))
            mapping_file = Path(script_dir) / "texture_mapping.json"
            mapping = {}
            if mapping_file.exists():
                mapping = ASTCTools.load_texture_mapping(mapping_file)
            
            temp_output = os.path.join(tempfile.gettempdir(), f"encoded_{texture_name}")
            texture_name_no_ext = os.path.splitext(texture_name)[0]
            
            success = False
            
            if texture_name_no_ext in DECODE_CACHE:
                success = ASTCTools.encode_with_cache(astcenc_path, Path(replacement_texture_path), Path(temp_output), texture_name_no_ext, "medium")
            elif mapping:
                success = ASTCTools.encode_texture(astcenc_path, Path(replacement_texture_path), Path(temp_output), 
                                                 mapping[texture_name_no_ext]['width'], 
                                                 mapping[texture_name_no_ext]['height'], 
                                                 8, 8, "medium", original_size)
            else:
                return False, "No encoding configuration found"
            
            if not success:
                return False, "Failed to encode texture"
            
            encoded_size = os.path.getsize(temp_output)
            if encoded_size != original_size:
                with open(temp_output, 'rb') as f:
                    encoded_data = f.read()
                
                padded_data = ASTCTools.pad_to_size(encoded_data, original_size)
                with open(temp_output, 'wb') as f:
                    f.write(padded_data)
            
            input_texture_path = os.path.join(input_textures_folder, texture_name)
            shutil.copy2(temp_output, input_texture_path)
            
            final_size = os.path.getsize(temp_output)
            
            output_corresponding_file = os.path.join(output_folder, "-2094201140079393352", texture_name)
            if os.path.exists(output_corresponding_file):
                input_corresponding_path = os.path.join(input_corresponding_folder, texture_name)
                shutil.copy2(output_corresponding_file, input_corresponding_path)
                
                success = TextureReplacer.hex_edit_file_size(input_corresponding_path, final_size)
                
                if success:
                    try:
                        os.remove(temp_output)
                    except:
                        pass
                    return True, f"Quest texture replaced. Size updated to {final_size} bytes."
                else:
                    return False, "Failed to update file size"
            else:
                try:
                    os.remove(temp_output)
                except:
                    pass
                return True, "Quest texture replaced (no corresponding file)"
                
        except Exception as e:
            return False, f"Quest replacement error: {str(e)}"

class RenderDocManager:
    """RenderDoc integration"""
    
    @staticmethod
    def find_renderdoc():
        common_paths = [
            os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'RenderDoc', 'qrenderdoc.exe'),
            os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'RenderDoc', 'qrenderdoc.exe'),
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    @staticmethod
    def open_with_renderdoc(renderdoc_path, texture_path):
        try:
            subprocess.Popen([renderdoc_path, texture_path])
            return True, "RenderDoc launched"
        except Exception as e:
            return False, f"RenderDoc failed: {str(e)}"

class EchoVRTextureViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("EchoVR Texture Editor - PCVR & Quest Support")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)
        
        self.set_window_icon()
        
        self.colors = {
            'bg_dark': '#0a0a1a',
            'bg_medium': '#1a1a3a',
            'bg_light': '#2a2a5a',
            'accent_blue': '#00a8ff',
            'accent_purple': '#9d4edd',
            'text_light': '#ffffff',
            'text_muted': '#b8b8d9',
            'success': '#4cd964',
            'warning': '#ffcc00',
            'error': '#ff6b6b'
        }
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.root.configure(bg=self.colors['bg_dark'])
        self.style.configure('.', background=self.colors['bg_dark'], foreground=self.colors['text_light'])
        
        self.config = ConfigManager.load_config()
        self.output_folder = self.config.get('output_folder')
        self.input_folder = self.config.get('input_folder')
        self.quest_input_folder = self.config.get('quest_input_folder')
        self.renderdoc_path = self.config.get('renderdoc_path')
        
        self.evr_tools = EVRToolsManager()
        self.data_folder = self.config.get('data_folder')
        self.extracted_folder = self.config.get('extracted_folder')
        self.repacked_folder = self.config.get('repacked_folder')
        self.package_name = None
        
        self.textures_folder = None
        self.corresponding_folder = None
        self.current_texture = None
        self.replacement_texture = None
        self.original_info = None
        self.replacement_info = None
        self.replacement_size = None
        
        self.is_quest_textures = False
        self.is_pcvr_textures = False
        
        self.texture_cache = {}
        self.all_textures = []
        self.filtered_textures = []
        
        self.is_loading_all = False
        self.textures_to_load = []
        self.current_batch_index = 0
        
        self.setup_ui()
        
        if self.output_folder and os.path.exists(self.output_folder):
            self.set_output_folder(self.output_folder)
        
        if self.input_folder and os.path.exists(self.input_folder):
            self.set_input_folder(self.input_folder)
            
        if self.quest_input_folder and os.path.exists(self.quest_input_folder):
            self.set_quest_input_folder(self.quest_input_folder)
            
        if self.data_folder and os.path.exists(self.data_folder):
            self.set_data_folder(self.data_folder)
            
        if self.extracted_folder and os.path.exists(self.extracted_folder):
            self.set_extracted_folder(self.extracted_folder)

    def set_window_icon(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            internal_dir = os.path.join(script_dir, "_internal")
            icon_path = os.path.join(internal_dir, "icon.ico")
            
            if os.path.exists(internal_dir) and os.path.exists(icon_path):
                if os.name == 'nt':
                    self.root.iconbitmap(icon_path)
                else:
                    try:
                        img = Image.open(icon_path)
                        photo = ImageTk.PhotoImage(img)
                        self.root.iconphoto(True, photo)
                        self.icon_image = photo
                    except:
                        pass
            
            if os.name == 'nt':
                try:
                    icon_path = os.path.abspath(icon_path)
                    if os.path.exists(icon_path):
                        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("EchoVR.TextureEditor.1.0")
                except Exception as e:
                    pass
        
        except Exception as e:
            pass

    def setup_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.grid(row=0, column=0, sticky='nsew')
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        self.style.configure('Custom.TEntry', 
                           fieldbackground='#2a2a5a',
                           foreground='#ffffff',
                           borderwidth=1,
                           focusthickness=1,
                           padding=5)
        
        header_frame = ttk.Frame(main_frame)
        header_frame.grid(row=0, column=0, columnspan=3, sticky='ew', pady=(0, 5))
        header_frame.columnconfigure(0, weight=1)
        
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            internal_dir = os.path.join(script_dir, "_internal")
            icon_path = os.path.join(internal_dir, "icon.ico")
            
            if os.path.exists(internal_dir) and os.path.exists(icon_path):
                img = Image.open(icon_path)
                img = img.resize((20, 20), Image.Resampling.LANCZOS)
                self.title_icon = ImageTk.PhotoImage(img)
                
                icon_label = tk.Label(header_frame, image=self.title_icon, bg=self.colors['bg_dark'])
                icon_label.grid(row=0, column=0, sticky='w', padx=(10, 5))
        except:
            pass
        
        title_label = tk.Label(header_frame, text="ECHO VR TEXTURE EDITOR - PCVR & QUEST SUPPORT", 
                              font=('Arial', 14, 'bold'), 
                              fg=self.colors['accent_blue'],
                              bg=self.colors['bg_dark'])
        title_label.grid(row=0, column=1, sticky='w')
        
        self.output_folder_button = tk.Button(header_frame, text="Select Output Folder", 
                                            command=self.select_output_folder,
                                            bg=self.colors['accent_blue'],
                                            fg=self.colors['text_light'],
                                            font=('Arial', 9, 'bold'))
        self.output_folder_button.grid(row=0, column=2, sticky='e', padx=5)
        
        self.input_folder_button = tk.Button(header_frame, text="Select PCVR Input", 
                                           command=self.select_input_folder,
                                           bg=self.colors['accent_purple'],
                                           fg=self.colors['text_light'],
                                           font=('Arial', 9, 'bold'))
        self.input_folder_button.grid(row=0, column=3, sticky='e', padx=5)
        
        self.quest_input_button = tk.Button(header_frame, text="Select Quest Input", 
                                          command=self.select_quest_input_folder,
                                          bg='#4cd964',
                                          fg=self.colors['text_light'],
                                          font=('Arial', 9, 'bold'))
        self.quest_input_button.grid(row=0, column=4, sticky='e', padx=5)
        
        self.install_adb_button = tk.Button(header_frame, text="Install ADB Tools", 
                                          command=self.install_adb_tools,
                                          bg='#ff9500',
                                          fg=self.colors['text_light'],
                                          font=('Arial', 9, 'bold'))
        self.install_adb_button.grid(row=0, column=5, sticky='e', padx=5)
        
        self.push_quest_button = tk.Button(header_frame, text="Push Files To Quest", 
                                         command=self.push_to_quest,
                                         bg='#ff9500',
                                         fg=self.colors['text_light'],
                                         font=('Arial', 9, 'bold'),
                                         state=tk.DISABLED)
        self.push_quest_button.grid(row=0, column=6, sticky='e', padx=5)
        
        self.status_label = tk.Label(main_frame, text="No folders selected",
                                   fg=self.colors['text_muted'], bg=self.colors['bg_dark'],
                                   font=('Arial', 9))
        self.status_label.grid(row=1, column=0, columnspan=3, sticky='ew', pady=(0, 5))
        
        self.platform_label = tk.Label(main_frame, text="Platform: Unknown",
                                     fg=self.colors['warning'], bg=self.colors['bg_dark'],
                                     font=('Arial', 10, 'bold'))
        self.platform_label.grid(row=2, column=0, columnspan=3, sticky='ew', pady=(0, 5))
        
        evr_frame = ttk.LabelFrame(main_frame, text="EVR TOOLS INTEGRATION", padding=5)
        evr_frame.grid(row=3, column=0, columnspan=3, sticky='ew', pady=(0, 5))
        evr_frame.columnconfigure(1, weight=1)
        
        ttk.Label(evr_frame, text="Data Folder:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.data_folder_label = ttk.Label(evr_frame, text="Not selected", foreground=self.colors['text_muted'])
        self.data_folder_label.grid(row=0, column=1, sticky='w', padx=5, pady=2)
        self.data_folder_button = ttk.Button(evr_frame, text="Select", command=self.select_data_folder)
        self.data_folder_button.grid(row=0, column=2, padx=5, pady=2)
        
        ttk.Label(evr_frame, text="Manifest:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        self.package_var = tk.StringVar()
        self.package_dropdown = ttk.Combobox(evr_frame, textvariable=self.package_var, state="readonly", width=30)
        self.package_dropdown.grid(row=1, column=1, sticky='ew', padx=5, pady=2)
        self.package_dropdown.bind('<<ComboboxSelected>>', self.on_package_selected)
        
        ttk.Label(evr_frame, text="Extracted Folder:").grid(row=2, column=0, sticky='w', padx=5, pady=2)
        self.extracted_folder_label = ttk.Label(evr_frame, text="Not selected", foreground=self.colors['text_muted'])
        self.extracted_folder_label.grid(row=2, column=1, sticky='w', padx=5, pady=2)
        self.extracted_folder_button = ttk.Button(evr_frame, text="Select", command=self.select_extracted_folder)
        self.extracted_folder_button.grid(row=2, column=2, padx=5, pady=2)
        
        button_frame = ttk.Frame(evr_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=5)
        
        self.extract_button = ttk.Button(button_frame, text="Extract Package", 
                                       command=self.extract_package, state=tk.DISABLED)
        self.extract_button.pack(side=tk.LEFT, padx=5)
        
        self.repack_button = ttk.Button(button_frame, text="Repack Modified", 
                                      command=self.repack_package, state=tk.DISABLED)
        self.repack_button.pack(side=tk.LEFT, padx=5)
        
        tool_status = "Tool: "
        if self.evr_tools.tool_path:
            tool_status += f"{os.path.basename(self.evr_tools.tool_path)} ✓"
        else:
            tool_status += "Not found ✗"
            
        self.evr_status_label = ttk.Label(evr_frame, text=tool_status, foreground=self.colors['text_muted'])
        self.evr_status_label.grid(row=4, column=0, columnspan=3, pady=2)
        
        left_frame = ttk.LabelFrame(main_frame, text="AVAILABLE TEXTURES", padding=5)
        left_frame.grid(row=4, column=0, sticky='nsew', padx=(0, 5))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)
        
        search_frame = ttk.Frame(left_frame)
        search_frame.grid(row=0, column=0, sticky='ew', pady=(0, 5))
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, style='Custom.TEntry')
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.search_entry.bind('<KeyRelease>', self.filter_textures)
        
        clear_btn = ttk.Button(search_frame, text="X", width=2, command=self.clear_search)
        clear_btn.pack(side=tk.LEFT)
        
        list_frame = ttk.Frame(left_frame)
        list_frame.grid(row=1, column=0, sticky='nsew')
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        self.file_list = tk.Listbox(list_frame, height=15, 
                                  bg=self.colors['bg_light'],
                                  fg=self.colors['text_light'],
                                  selectbackground=self.colors['accent_blue'])
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=scrollbar.set)
        
        self.file_list.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.file_list.bind('<<ListboxSelect>>', self.on_texture_selected)
        
        middle_frame = ttk.LabelFrame(main_frame, text="ORIGINAL TEXTURE", padding=5)
        middle_frame.grid(row=4, column=1, sticky='nsew', padx=5)
        middle_frame.columnconfigure(0, weight=1)
        middle_frame.rowconfigure(0, weight=1)
        
        self.original_canvas = tk.Canvas(middle_frame, bg=self.colors['bg_medium'])
        self.original_canvas.grid(row=0, column=0, sticky='nsew')
        
        right_frame = ttk.LabelFrame(main_frame, text="REPLACEMENT TEXTURE", padding=5)
        right_frame.grid(row=4, column=2, sticky='nsew', padx=(5, 0))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        
        self.replacement_canvas = tk.Canvas(right_frame, bg=self.colors['bg_medium'])
        self.replacement_canvas.grid(row=0, column=0, sticky='nsew')
        self.replacement_canvas.bind("<Button-1>", self.browse_replacement_texture)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=3, sticky='ew', pady=(10, 0))
        
        self.edit_button = tk.Button(button_frame, text="Open in Editor", 
                                   command=self.open_external_editor,
                                   bg=self.colors['accent_blue'],
                                   fg=self.colors['text_light'],
                                   font=('Arial', 9, 'bold'),
                                   state=tk.DISABLED)
        self.edit_button.pack(side=tk.LEFT, padx=5)
        
        self.renderdoc_button = tk.Button(button_frame, text="Open in RenderDoc", 
                                        command=self.open_renderdoc,
                                        bg=self.colors['accent_purple'],
                                        fg=self.colors['text_light'],
                                        font=('Arial', 9, 'bold'),
                                        state=tk.DISABLED)
        self.renderdoc_button.pack(side=tk.LEFT, padx=5)
        
        self.replace_button = tk.Button(button_frame, text="Replace Texture", 
                                      command=self.replace_texture,
                                      bg=self.colors['accent_blue'],
                                      fg=self.colors['text_light'],
                                      font=('Arial', 9, 'bold'),
                                      state=tk.DISABLED)
        self.replace_button.pack(side=tk.LEFT, padx=5)
        
        self.load_all_button = tk.Button(button_frame, text="Load All Textures", 
                                       command=self.start_loading_all_textures,
                                       bg='#4cd964',
                                       fg=self.colors['text_light'],
                                       font=('Arial', 9, 'bold'))
        self.load_all_button.pack(side=tk.LEFT, padx=5)
        
        self.resolution_status = tk.Label(button_frame, text="",
                                        fg=self.colors['text_muted'], bg=self.colors['bg_dark'],
                                        font=('Arial', 9))
        self.resolution_status.pack(side=tk.LEFT, padx=10)
        
        info_frame = ttk.LabelFrame(main_frame, text="TEXTURE INFORMATION", padding=5)
        info_frame.grid(row=6, column=0, columnspan=3, sticky='nsew', pady=(10, 0))
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(0, weight=1)
        
        self.info_text = scrolledtext.ScrolledText(info_frame, height=6, wrap=tk.WORD,
                                                 bg=self.colors['bg_light'],
                                                 fg=self.colors['text_light'],
                                                 font=('Arial', 9))
        self.info_text.grid(row=0, column=0, sticky='nsew')
        
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=2)
        main_frame.columnconfigure(2, weight=2)
        main_frame.rowconfigure(4, weight=3)
        main_frame.rowconfigure(6, weight=1)
        
        self.update_canvas_placeholder(self.original_canvas, "Select output folder to view textures")
        self.update_canvas_placeholder(self.replacement_canvas, "Click to select replacement texture")

    def update_canvas_placeholder(self, canvas, text):
        canvas.delete("all")
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width, canvas_height = 400, 300
            
        canvas.create_text(canvas_width//2, canvas_height//2, 
                          text=text, font=("Arial", 10), 
                          fill=self.colors['text_muted'], justify=tk.CENTER)

    def log_info(self, message):
        self.info_text.insert(tk.END, message + "\n")
        self.info_text.see(tk.END)
        self.info_text.update_idletasks()

    def install_adb_tools(self):
        """Install ADB Platform Tools"""
        self.log_info("Installing ADB Platform Tools...")
        def install_thread():
            success, message = ADBManager.install_adb_tools()
            self.root.after(0, lambda: self.on_adb_install_complete(success, message))
        threading.Thread(target=install_thread, daemon=True).start()

    def on_adb_install_complete(self, success, message):
        if success:
            self.log_info(f"✅ ADB Tools installed: {message}")
            messagebox.showinfo("Success", "ADB Platform Tools installed successfully!")
            self.test_adb_connection()
        else:
            self.log_info(f"❌ ADB installation failed: {message}")
            messagebox.showerror("Error", f"ADB installation failed: {message}")

    def test_adb_connection(self):
        """Test ADB connection"""
        self.log_info("Testing ADB connection...")
        def test_thread():
            success, message, adb_path = ADBManager.check_adb()
            self.root.after(0, lambda: self.on_adb_test_complete(success, message))
        threading.Thread(target=test_thread, daemon=True).start()

    def on_adb_test_complete(self, success, message):
        if success:
            self.log_info(f"✅ ADB: {message}")
            if self.is_quest_textures:
                self.push_quest_button.config(state=tk.NORMAL, bg='#ff9500')
        else:
            self.log_info(f"❌ ADB: {message}")
            self.push_quest_button.config(state=tk.DISABLED, bg='#666666')

    def update_quest_push_button(self):
        """Enable/disable Push to Quest button"""
        if self.is_quest_textures and self.output_folder:
            self.test_adb_connection()
        else:
            self.push_quest_button.config(state=tk.DISABLED, bg='#666666')

    def push_to_quest(self):
        """Push files to Quest"""
        if not self.output_folder:
            messagebox.showerror("Error", "Please select output folder first")
            return
            
        success, message, _ = ADBManager.check_adb()
        if not success:
            messagebox.showerror("ADB Error", f"Cannot connect to Quest:\n{message}")
            return
        
        result = messagebox.askyesno(
            "Push to Quest", 
            "This will push files to your Quest headset.\n\nContinue?",
            icon='warning'
        )
        
        if not result:
            return
            
        self.log_info("🚀 Starting Quest file push...")
        self.push_quest_button.config(state=tk.DISABLED, bg='#666666', text="Pushing...")
        self.root.update_idletasks()
        
        def push_thread():
            try:
                push_folder = self.output_folder
                if self.repacked_folder and os.path.exists(self.repacked_folder):
                    if (os.path.exists(os.path.join(self.repacked_folder, "manifests")) or 
                        os.path.exists(os.path.join(self.repacked_folder, "packages"))):
                        push_folder = self.repacked_folder
                        self.log_info("📦 Using repacked folder")
                
                quest_dest_path = "/sdcard/readyatdawn/files/_data/5932408047/rad15/android"
                
                success, message = ADBManager.push_to_quest(push_folder, quest_dest_path)
                
                if success:
                    self.root.after(0, lambda: self.on_quest_push_complete(True, message))
                else:
                    self.root.after(0, lambda: self.on_quest_push_complete(False, message))
                    
            except Exception as thread_error:
                error_message = f"Push thread error: {str(thread_error)}"
                self.root.after(0, lambda: self.on_quest_push_complete(False, error_message))
        
        threading.Thread(target=push_thread, daemon=True).start()

    def on_quest_push_complete(self, success, message):
        if success:
            messagebox.showinfo("Success", f"Files pushed to Quest!\n\n{message}")
            self.log_info(f"✅ QUEST PUSH: {message}")
        else:
            messagebox.showerror("Error", f"Failed to push files:\n{message}")
            self.log_info(f"❌ QUEST PUSH FAILED: {message}")
        
        self.push_quest_button.config(state=tk.NORMAL, bg='#ff9500', text="Push Files To Quest")
        self.update_quest_push_button()

    def select_output_folder(self):
        path = filedialog.askdirectory(title="Select Output Folder (contains original textures)")
        if path:
            self.set_output_folder(path)
            
    def set_output_folder(self, path):
        self.output_folder = path
        
        quest_textures_folder = os.path.join(path, "5231972605540061417")
        pcvr_textures_folder = os.path.join(path, "-4707359568332879775")
        
        if os.path.exists(quest_textures_folder):
            self.textures_folder = quest_textures_folder
            self.corresponding_folder = os.path.join(path, "-2094201140079393352")
            self.detect_texture_type(quest_textures_folder)
        elif os.path.exists(pcvr_textures_folder):
            self.textures_folder = pcvr_textures_folder
            self.corresponding_folder = os.path.join(path, "5353709876897953952")
            self.detect_texture_type(pcvr_textures_folder)
        else:
            messagebox.showerror("Error", "Texture folder not found! Make sure the output folder contains:\n5231972605540061417 (Quest) or -4707359568332879775 (PCVR)")
            return
        
        if os.path.exists(self.textures_folder):
            platform_text = "Quest" if self.is_quest_textures else "PCVR"
            self.status_label.config(text=f"Output folder: {os.path.basename(path)} ({platform_text})")
            self.log_info(f"Output folder set: {path} ({platform_text})")
            self.load_textures()
            ConfigManager.save_config(output_folder=self.output_folder)
            self.update_quest_push_button()
            
    def select_input_folder(self):
        path = filedialog.askdirectory(title="Select PCVR Input Folder (where modified PCVR textures go)")
        if path:
            self.set_input_folder(path)
            
    def set_input_folder(self, path):
        self.input_folder = path
        self.status_label.config(text=f"PCVR Input folder: {os.path.basename(path)}")
        self.log_info(f"PCVR Input folder set: {path}")
        ConfigManager.save_config(input_folder=self.input_folder)
        
    def select_quest_input_folder(self):
        path = filedialog.askdirectory(title="Select Quest Input Folder (where modified Quest textures go)")
        if path:
            self.set_quest_input_folder(path)
            
    def set_quest_input_folder(self, path):
        self.quest_input_folder = path
        self.status_label.config(text=f"Quest Input folder: {os.path.basename(path)}")
        self.log_info(f"Quest Input folder set: {path}")
        ConfigManager.save_config(quest_input_folder=self.quest_input_folder)
        self.update_quest_push_button()
            
    def select_data_folder(self):
        path = filedialog.askdirectory(title="Select Data Folder (contains manifests and packages)")
        if path:
            self.set_data_folder(path)
    
    def set_data_folder(self, path):
        self.data_folder = path
        self.data_folder_label.config(text=os.path.basename(path))
        
        manifests_path = os.path.join(path, "manifests")
        packages_path = os.path.join(path, "packages")
        
        if not os.path.exists(manifests_path) or not os.path.exists(packages_path):
            parent_path = os.path.dirname(path)
            parent_manifests = os.path.join(parent_path, "manifests")
            parent_packages = os.path.join(parent_path, "packages")
            
            if os.path.exists(parent_manifests) and os.path.exists(parent_packages):
                path = parent_path
                manifests_path = parent_manifests
                packages_path = parent_packages
                self.data_folder = path
                self.data_folder_label.config(text=os.path.basename(path))
        
        if os.path.exists(manifests_path) and os.path.exists(packages_path):
            self.populate_package_dropdown(manifests_path)
            self.log_info(f"Manifests found: {manifests_path}")
            self.log_info(f"Packages found: {packages_path}")
        else:
            self.log_info("Could not find manifests and packages folders")
        
        ConfigManager.save_config(data_folder=self.data_folder)
        self.update_evr_buttons_state()
    
    def populate_package_dropdown(self, manifests_path):
        try:
            packages = []
            for file_name in os.listdir(manifests_path):
                if os.path.isfile(os.path.join(manifests_path, file_name)):
                    packages_path = os.path.join(os.path.dirname(manifests_path), "packages")
                    package_file = os.path.join(packages_path, file_name)
                    package_file_0 = os.path.join(packages_path, f"{file_name}_0")
                    
                    if os.path.exists(package_file) or os.path.exists(package_file_0):
                        packages.append(file_name)
            
            filtered_packages = [pkg for pkg in packages if pkg == "48037dc70b0ecab2"]
            if not filtered_packages and packages:
                filtered_packages = [packages[0]]
            
            self.package_dropdown['values'] = filtered_packages
            if filtered_packages:
                self.package_dropdown.current(0)
                self.on_package_selected(None)
                self.log_info(f"Found {len(packages)} packages, showing: {filtered_packages[0]}")
            else:
                self.log_info("No valid packages found")
        except Exception as e:
            self.log_info(f"Error reading manifests: {e}")
    
    def on_package_selected(self, event):
        self.package_name = self.package_var.get()
        try:
            int(self.package_name, 16)
            self.update_evr_buttons_state()
        except ValueError:
            self.extract_button.config(state=tk.DISABLED)
            self.repack_button.config(state=tk.DISABLED)
    
    def select_extracted_folder(self):
        path = filedialog.askdirectory(title="Select Extracted Folder")
        if path:
            self.set_extracted_folder(path)
    
    def set_extracted_folder(self, path):
        self.extracted_folder = path
        self.extracted_folder_label.config(text=os.path.basename(path))
        self.update_evr_buttons_state()
        ConfigManager.save_config(extracted_folder=self.extracted_folder)
    
    def update_evr_buttons_state(self):
        if self.data_folder and self.package_name and self.extracted_folder:
            self.extract_button.config(state=tk.NORMAL)
            
            if os.path.exists(self.extracted_folder) and any(os.listdir(self.extracted_folder)):
                self.repack_button.config(state=tk.NORMAL)
            else:
                self.repack_button.config(state=tk.DISABLED)
        else:
            self.extract_button.config(state=tk.DISABLED)
            self.repack_button.config(state=tk.DISABLED)
    
    def extract_package(self):
        if not all([self.data_folder, self.package_name, self.extracted_folder]):
            messagebox.showerror("Error", "Please select data folder, package, and extraction folder first.")
            return
        
        os.makedirs(self.extracted_folder, exist_ok=True)
        
        self.evr_status_label.config(text="Extracting package...", foreground=self.colors['accent_blue'])
        self.root.update_idletasks()
        
        def extraction_thread():
            success, message = self.evr_tools.extract_package(
                self.data_folder, 
                self.package_name, 
                self.extracted_folder
            )
            
            self.root.after(0, lambda: self.on_extraction_complete(success, message))
        
        threading.Thread(target=extraction_thread, daemon=True).start()
    
    def on_extraction_complete(self, success, message):
        if success:
            self.evr_status_label.config(text="Extraction successful!", foreground=self.colors['success'])
            self.log_info(f"✓ EXTRACTION: {message}")
            
            extracted_textures_path = self.find_extracted_textures(self.extracted_folder)
            
            if extracted_textures_path:
                self.set_output_folder(extracted_textures_path)
            else:
                self.set_output_folder(self.extracted_folder)
            
            self.repack_button.config(state=tk.NORMAL)
        else:
            self.evr_status_label.config(text="Extraction failed", foreground=self.colors['error'])
            self.log_info(f"✗ EXTRACTION FAILED: {message}")
            messagebox.showerror("Extraction Error", message)
    
    def find_extracted_textures(self, base_dir):
        texture_patterns = [
            os.path.join(base_dir, "**", "-4707359568332879775"),
            os.path.join(base_dir, "**", "5231972605540061417"),
            os.path.join(base_dir, "**", "textures"),
        ]
        
        for pattern in texture_patterns:
            for path in glob.glob(pattern, recursive=True):
                if os.path.isdir(path):
                    return os.path.dirname(path)
        
        return None
    
    def repack_package(self):
        if not all([self.data_folder, self.package_name, self.extracted_folder]):
            messagebox.showerror("Error", "Please select data folder, package, and extraction folder first.")
            return

        if self.is_quest_textures and self.quest_input_folder:
            input_folder = self.quest_input_folder
            self.log_info("🎯 Using Quest input folder for repacking")
        elif self.input_folder:
            input_folder = self.input_folder
            self.log_info("🎯 Using PCVR input folder for repacking")
        else:
            messagebox.showerror("Error", "Please select the appropriate input folder first.")
            return
        
        output_dir = filedialog.askdirectory(title="Select Output Directory for Repacked Package")
        if not output_dir:
            return
        
        self.repacked_folder = output_dir
        ConfigManager.save_config(repacked_folder=output_dir)
        
        self.evr_status_label.config(text="Repacking package...", foreground=self.colors['accent_blue'])
        self.root.update_idletasks()
        
        def repacking_thread():
            success, message = self.evr_tools.repack_package(
                output_dir, 
                self.package_name, 
                self.data_folder, 
                input_folder  # Use the correct input folder
            )
            
            self.root.after(0, lambda: self.on_repacking_complete(success, message, output_dir))
        
        threading.Thread(target=repacking_thread, daemon=True).start()

    def on_repacking_complete(self, success, message, output_dir):
        if success:
            self.evr_status_label.config(text="Repacking successful!", foreground=self.colors['success'])
            self.log_info(f"✓ REPACKING: {message}")
            
            packages_path = os.path.join(output_dir, "packages")
            manifests_path = os.path.join(output_dir, "manifests")
            
            if os.path.exists(packages_path) and os.path.exists(manifests_path):
                self.log_info(f"✓ Packages and manifests created in: {output_dir}")
                self.update_quest_push_button()
            else:
                self.log_info("⚠ Packages or manifests folders not found in output directory")
            
        else:
            self.evr_status_label.config(text="Repacking failed", foreground=self.colors['error'])
            self.log_info(f"✗ REPACKING FAILED: {message}")
        
        messagebox.showinfo("Repacking Result", message)

    def detect_texture_type(self, textures_folder):
        folder_name = os.path.basename(textures_folder)
        if folder_name == "5231972605540061417":
            self.is_quest_textures = True
            self.is_pcvr_textures = False
            self.platform_label.config(text="Platform: Quest (ASTC)", fg=self.colors['success'])
            self.root.after(1000, self.update_quest_push_button)
        elif folder_name == "-4707359568332879775":
            self.is_quest_textures = False
            self.is_pcvr_textures = True
            self.platform_label.config(text="Platform: PCVR (DDS)", fg=self.colors['accent_blue'])
            self.push_quest_button.config(state=tk.DISABLED, bg='#666666')
        else:
            self.is_quest_textures = False
            self.is_pcvr_textures = False
            self.platform_label.config(text="Platform: Unknown", fg=self.colors['warning'])
            self.push_quest_button.config(state=tk.DISABLED, bg='#666666')

    def filter_textures(self, event=None):
        search_text = self.search_var.get().lower()
        
        if not search_text:
            self.filtered_textures = self.all_textures.copy()
        else:
            self.filtered_textures = [texture for texture in self.all_textures if search_text in texture.lower()]
        
        self.file_list.delete(0, tk.END)
        for texture in self.filtered_textures:
            self.file_list.insert(tk.END, texture)
            
        self.status_label.config(text=f"Thanks for using EVR Texture Editor")

    def clear_search(self):
        self.search_var.set("")
        self.filter_textures()
        
    def load_texture_cache(self):
        """Load texture cache from cache.json for filtering - only for Quest textures"""
        if self.is_quest_textures:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            cache_path = os.path.join(script_dir, "cache.json")
            
            print(f"🔍 Looking for cache.json at: {cache_path}")
            
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, 'r') as f:
                        cache_data = json.load(f)
                    
                    self.texture_cache = {key: True for key in cache_data.keys()}
                    print(f"✅ Loaded texture cache from {cache_path}: {len(self.texture_cache)} textures identified")
                    
                except Exception as e:
                    print(f"❌ Error loading cache.json: {e}")
                    self.texture_cache = {}
            else:
                if self.output_folder:
                    cache_path = os.path.join(self.output_folder, "cache.json")
                    print(f"🔍 Looking for cache.json at: {cache_path}")
                    
                    if os.path.exists(cache_path):
                        try:
                            with open(cache_path, 'r') as f:
                                cache_data = json.load(f)
                            
                            self.texture_cache = {key: True for key in cache_data.keys()}
                            print(f"✅ Loaded texture cache from {cache_path}: {len(self.texture_cache)} textures identified")
                        except Exception as e:
                            print(f"❌ Error loading cache.json: {e}")
                            self.texture_cache = {}
                    else:
                        print(f"❌ cache.json not found in script directory or output folder")
                        self.texture_cache = {}
                else:
                    print(f"❌ cache.json not found in script directory")
                    self.texture_cache = {}
        else:
            print("🔍 PCVR mode - not using cache.json, showing all DDS files")
            self.texture_cache = {}

    def is_texture_file(self, file_name):
        """Check if a file is a texture based on cache.json (Quest) or DDS signature (PCVR)"""
        if self.is_quest_textures and self.texture_cache:
            name_without_ext = os.path.splitext(file_name)[0]
            
            if file_name in self.texture_cache:
                print(f"✅ Texture found in cache: {file_name}")
                return True
            elif name_without_ext in self.texture_cache:
                print(f"✅ Texture found in cache (without extension): {name_without_ext}")
                return True
            else:
                print(f"❌ File not in cache (filtered out): {file_name}")
                return False
        elif self.is_pcvr_textures:
            file_path = os.path.join(self.textures_folder, file_name)
            try:
                with open(file_path, 'rb') as f:
                    signature = f.read(4)
                    if signature == b'DDS ':
                        print(f"✅ Valid DDS file: {file_name}")
                        return True
                    else:
                        print(f"❌ Not a DDS file (filtered out): {file_name}")
                        return False
            except:
                if file_name.lower().endswith('.dds'):
                    print(f"✅ DDS file (by extension): {file_name}")
                    return True
                else:
                    print(f"❌ Not a DDS file (filtered out): {file_name}")
                    return False
        
        print(f"⚠️ No specific filtering - showing file: {file_name}")
        return True

    def load_textures(self):
        self.file_list.delete(0, tk.END)
        self.file_list.insert(tk.END, "Loading textures...")
        self.update_canvas_placeholder(self.original_canvas, "Loading textures...")
        self.root.update_idletasks()
        
        self.load_texture_cache()
        
        try:
            texture_count = 0
            texture_files = []
            
            if not os.path.exists(self.textures_folder):
                self.log_info("Textures folder not found!")
                return
                
            print(f"🔍 Scanning folder: {self.textures_folder}")
            all_files = os.listdir(self.textures_folder)
            print(f"📁 Found {len(all_files)} files in folder")
            
            for file_name in all_files:
                file_path = os.path.join(self.textures_folder, file_name)
                if os.path.isfile(file_path):
                    print(f"📄 Checking file: {file_name}")
                    
                    if not self.is_texture_file(file_name):
                        print(f"❌ Filtered out: {file_name}")
                        continue
                        
                    texture_files.append(file_name)
                    texture_count += 1
                    print(f"✅ Added texture: {file_name}")
            
            self.all_textures = sorted(texture_files)
            self.filtered_textures = self.all_textures.copy()
            
            self.file_list.delete(0, tk.END)
            for file_name in self.filtered_textures:
                self.file_list.insert(tk.END, file_name)
                
            platform_text = "Quest" if self.is_quest_textures else "PCVR"
            cache_info = f" (filtered by cache)" if self.is_quest_textures and self.texture_cache else " (all DDS files)" if self.is_pcvr_textures else ""
            status_text = f"Found {texture_count} {platform_text} texture files{cache_info}"
            self.status_label.config(text=status_text)
            self.log_info(f"Found {texture_count} {platform_text} texture files{cache_info}")
            
            if texture_count == 0:
                self.log_info("No texture files found.")
                self.update_canvas_placeholder(self.original_canvas, "No textures found")
            else:
                self.update_canvas_placeholder(self.original_canvas, "Select a texture to view")
                
        except Exception as e:
            self.log_info(f"Error loading textures: {e}")
            self.update_canvas_placeholder(self.original_canvas, "Error loading textures")
                
    def on_texture_selected(self, event):
        if not self.file_list.curselection():
            return
            
        index = self.file_list.curselection()[0]
        texture_name = self.filtered_textures[index]
        self.current_texture = os.path.join(self.textures_folder, texture_name)
        
        try:
            self.update_canvas_placeholder(self.original_canvas, "Loading texture...")
            self.root.update_idletasks()
            
            def load_texture_thread():
                try:
                    image = TextureLoader.load_texture(self.current_texture, self.is_quest_textures)
                    self.root.after(0, lambda: self.display_texture_result(image))
                except Exception as e:
                    self.root.after(0, lambda: self.display_texture_error(e))
            
            threading.Thread(target=load_texture_thread, daemon=True).start()
            
        except Exception as e:
            self.log_info(f"Error loading texture: {e}")
            self.update_canvas_placeholder(self.original_canvas, "Error loading texture")
    
    def display_texture_result(self, image):
        if image:
            self.display_image_on_canvas(image, self.original_canvas)
            
            if self.is_quest_textures:
                self.original_info = {
                    'file_size': os.path.getsize(self.current_texture),
                    'format': 'ASTC',
                    'width': image.width,
                    'height': image.height
                }
            else:
                self.original_info = DDSHandler.get_dds_info(self.current_texture)
            
            self.update_texture_info()
            self.edit_button.config(state=tk.NORMAL, bg=self.colors['accent_blue'])
            self.renderdoc_button.config(state=tk.NORMAL, bg=self.colors['accent_purple'])
            self.replace_button.config(state=tk.NORMAL, bg=self.colors['accent_blue'])
        else:
            self.update_canvas_placeholder(self.original_canvas, "Failed to load texture")
            self.edit_button.config(state=tk.DISABLED, bg='#666666')
            self.renderdoc_button.config(state=tk.DISABLED, bg='#666666')
            self.replace_button.config(state=tk.DISABLED, bg='#666666')
    
    def display_texture_error(self, error):
        self.log_info(f"Error loading texture: {error}")
        self.update_canvas_placeholder(self.original_canvas, "Error loading texture")
        self.edit_button.config(state=tk.DISABLED, bg='#666666')
        self.renderdoc_button.config(state=tk.DISABLED, bg='#666666')
        self.replace_button.config(state=tk.DISABLED, bg='#666666')
            
    def browse_replacement_texture(self, event):
        if not self.current_texture:
            messagebox.showinfo("Info", "Please select an original texture first")
            return
            
        file_types = [("PNG files", "*.png"), ("DDS files", "*.dds"), ("All files", "*.*")]
        if self.is_quest_textures:
            file_types = [("PNG files", "*.png"), ("All files", "*.*")]
            
        file_path = filedialog.askopenfilename(
            title="Select Replacement Texture",
            filetypes=file_types
        )
        
        if file_path:
            self.replacement_texture = file_path
            try:
                def load_replacement_thread():
                    try:
                        if self.is_quest_textures:
                            image = Image.open(file_path).convert("RGBA")
                        else:
                            image = TextureLoader.load_texture(file_path, False)
                        self.root.after(0, lambda: self.display_replacement_result(image, file_path))
                    except Exception as e:
                        self.root.after(0, lambda: self.display_replacement_error(e))
                
                threading.Thread(target=load_replacement_thread, daemon=True).start()
                
            except Exception as e:
                self.log_info(f"Error loading replacement texture: {e}")
                self.update_canvas_placeholder(self.replacement_canvas, "Error loading replacement")
    
    def display_replacement_result(self, image, file_path):
        if image:
            self.display_image_on_canvas(image, self.replacement_canvas)
            
            if self.is_quest_textures:
                self.replacement_info = {
                    'file_size': os.path.getsize(file_path),
                    'format': 'PNG',
                    'width': image.width,
                    'height': image.height
                }
                self.replacement_size = None
            else:
                self.replacement_info = DDSHandler.get_dds_info(file_path)
                self.replacement_size = self.replacement_info['file_size']
                
            self.update_texture_info()
            self.check_resolution_match()
            self.log_info(f"Replacement loaded: {os.path.basename(file_path)}")
            if self.replacement_size:
                self.log_info(f"Replacement size: {self.replacement_size} bytes")
        else:
            self.update_canvas_placeholder(self.replacement_canvas, "Failed to load replacement")
    
    def display_replacement_error(self, error):
        self.log_info(f"Error loading replacement texture: {error}")
        self.update_canvas_placeholder(self.replacement_canvas, "Error loading replacement")
            
    def display_image_on_canvas(self, image, canvas):
        canvas.delete("all")
        
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width, canvas_height = 400, 300
        
        img_width, img_height = image.size
        ratio = min(canvas_width / img_width, canvas_height / img_height)
        new_size = (int(img_width * ratio), int(img_height * ratio))
        
        resized_image = image.resize(new_size, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(resized_image)
        
        x_pos = (canvas_width - new_size[0]) // 2
        y_pos = (canvas_height - new_size[1]) // 2
        
        canvas.create_image(x_pos, y_pos, anchor=tk.NW, image=photo)
        canvas.image = photo
        
    def update_texture_info(self):
        info = ""
        
        if self.original_info:
            platform_text = "Quest" if self.is_quest_textures else "PCVR"
            info += f"=== ORIGINAL TEXTURE ({platform_text}) ===\n"
            info += f"File: {os.path.basename(self.current_texture)}\n"
            info += f"Size: {self.original_info['file_size']:,} bytes\n"
            if 'width' in self.original_info and 'height' in self.original_info:
                info += f"Dimensions: {self.original_info['width']} x {self.original_info['height']}\n"
            info += f"Format: {self.original_info['format']}\n"
            if 'mipmaps' in self.original_info:
                info += f"Mipmaps: {self.original_info.get('mipmaps', 1)}\n"
            info += "\n"
        
        if self.replacement_info:
            info += "=== REPLACEMENT TEXTURE ===\n"
            info += f"File: {os.path.basename(self.replacement_texture)}\n"
            info += f"Size: {self.replacement_info['file_size']:,} bytes\n"
            if 'width' in self.replacement_info and 'height' in self.replacement_info:
                info += f"Dimensions: {self.replacement_info['width']} x {self.replacement_info['height']}\n"
            info += f"Format: {self.replacement_info['format']}\n"
            if 'mipmaps' in self.replacement_info:
                info += f"Mipmaps: {self.replacement_info.get('mipmaps', 1)}\n"
            info += "\n"
        
        if self.original_info and self.replacement_info:
            info += "=== COMPARISON ===\n"
            
            if 'width' in self.original_info and 'height' in self.original_info and 'width' in self.replacement_info and 'height' in self.replacement_info:
                orig_width = self.original_info['width']
                orig_height = self.original_info['height']
                rep_width = self.replacement_info['width']
                rep_height = self.replacement_info['height']
                
                if orig_width == rep_width and orig_height == rep_height:
                    info += "✓ Dimensions match\n"
                else:
                    info += f"✗ Dimension mismatch: {orig_width}x{orig_height} vs {rep_width}x{rep_height}\n"
            
            orig_format = self.original_info['format']
            rep_format = self.replacement_info['format']
            
            if self.is_quest_textures:
                info += "⚠ Quest texture - will be encoded to ASTC\n"
            elif orig_format == rep_format:
                info += f"✓ Format match: {orig_format}\n"
            else:
                info += f"⚠ Format difference: {orig_format} vs {rep_format}\n"
                
            if not self.is_quest_textures and self.replacement_size:
                orig_size = self.original_info['file_size']
                rep_size = self.replacement_size
                size_diff = rep_size - orig_size
                size_percent = (size_diff / orig_size) * 100 if orig_size > 0 else 0
                
                if abs(size_percent) < 10:
                    info += f"✓ Size similar: {orig_size:,} vs {rep_size:,} bytes ({size_percent:+.1f}%)\n"
                else:
                    info += f"⚠ Size difference: {orig_size:,} vs {rep_size:,} bytes ({size_percent:+.1f}%)\n"
        
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, info)
            
    def check_resolution_match(self):
        if self.original_info and self.replacement_info and 'width' in self.original_info and 'height' in self.original_info and 'width' in self.replacement_info and 'height' in self.replacement_info:
            orig_width = self.original_info['width']
            orig_height = self.original_info['height']
            rep_width = self.replacement_info['width']
            rep_height = self.replacement_info['height']
            
            if orig_width == rep_width and orig_height == rep_height:
                self.resolution_status.config(
                    text="✓ Resolutions match", 
                    fg=self.colors['success']
                )
            else:
                self.resolution_status.config(
                    text="✗ Resolutions don't match", 
                    fg=self.colors['warning']
                )
        else:
            self.resolution_status.config(text="")
            
    def open_external_editor(self):
        if not self.current_texture:
            return
            
        try:
            if sys.platform == 'win32':
                os.startfile(self.current_texture)
            elif sys.platform == 'darwin':
                subprocess.call(('open', self.current_texture))
            else:
                subprocess.call(('xdg-open', self.current_texture))
        except Exception as e:
            messagebox.showerror("Error", f"Could not open external editor: {str(e)}")
            
    def open_renderdoc(self):
        if not self.current_texture:
            return
            
        if not self.renderdoc_path:
            path = filedialog.askopenfilename(
                title="Locate RenderDoc Executable",
                filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
            )
            
            if path and os.path.exists(path):
                self.renderdoc_path = path
                ConfigManager.save_config(renderdoc_path=path)
            else:
                messagebox.showerror("Error", "RenderDoc not found.")
                return
        
        success, message = RenderDocManager.open_with_renderdoc(self.renderdoc_path, self.current_texture)
        
        if success:
            self.log_info(f"✓ {message}")
        else:
            messagebox.showerror("Error", message)
            self.log_info(f"✗ {message}")
            
    def replace_texture(self):
        if not self.current_texture or not self.replacement_texture or not self.output_folder:
            return
            
        if self.is_quest_textures:
            if not self.quest_input_folder:
                messagebox.showerror("Error", "Please select Quest input folder first")
                return
                
            success, message = TextureReplacer.replace_quest_texture(
                self.output_folder,
                self.quest_input_folder,
                self.current_texture, 
                self.replacement_texture,
                self.texture_cache
            )
        else:
            if not self.input_folder:
                messagebox.showerror("Error", "Please select PCVR input folder first")
                return
                
            if self.replacement_info and 'file_size' in self.replacement_info:
                replacement_size = self.replacement_info['file_size']
                
                success, message = TextureReplacer.replace_pcvr_texture(
                    self.output_folder,
                    self.input_folder,
                    self.current_texture, 
                    self.replacement_texture,
                    replacement_size
                )
            else:
                messagebox.showerror("Error", "Could not determine replacement file size")
                self.log_info("✗ Could not determine replacement file size")
                return
        
        if success:
            messagebox.showinfo("Success", message)
            platform_text = "Quest" if self.is_quest_textures else "PCVR"
            self.log_info(f"✓ {platform_text.upper()} REPLACEMENT: {message}")
            self.on_texture_selected(None)
        else:
            messagebox.showerror("Error", message)
            platform_text = "Quest" if self.is_quest_textures else "PCVR"
            self.log_info(f"✗ {platform_text.upper()} REPLACEMENT FAILED: {message}")
            
    def start_loading_all_textures(self):
        if not self.textures_folder or not os.path.exists(self.textures_folder):
            messagebox.showerror("Error", "No textures folder selected")
            return
            
        if self.is_loading_all:
            self.is_loading_all = False
            self.load_all_button.config(text="Load All Textures", bg='#4cd964')
            self.log_info("Stopped loading textures")
            return
            
        self.textures_to_load = []
        for file_name in os.listdir(self.textures_folder):
            file_path = os.path.join(self.textures_folder, file_name)
            if os.path.isfile(file_path):
                if self.is_texture_file(file_name):
                    self.textures_to_load.append(file_name)
        
        if not self.textures_to_load:
            self.log_info("No textures found to load")
            return
            
        self.is_loading_all = True
        self.current_batch_index = 0
        self.load_all_button.config(text="Stop Loading", bg='#ff6b6b')
        platform_text = "Quest" if self.is_quest_textures else "PCVR"
        self.log_info(f"Starting to load {len(self.textures_to_load)} {platform_text} textures in batches of 30")
        
        self.load_next_batch()

    def load_next_batch(self):
        if not self.is_loading_all or self.current_batch_index >= len(self.textures_to_load):
            self.is_loading_all = False
            self.load_all_button.config(text="Load All Textures", bg='#4cd964')
            self.log_info("Finished loading all textures")
            return
            
        batch_size = min(30, len(self.textures_to_load) - self.current_batch_index)
        batch_textures = self.textures_to_load[self.current_batch_index:self.current_batch_index + batch_size]
        
        self.log_info(f"Loading batch {self.current_batch_index//30 + 1}: {batch_size} textures")
        
        for texture_name in batch_textures:
            texture_path = os.path.join(self.textures_folder, texture_name)
            
            def load_texture_thread(texture_path=texture_path):
                try:
                    image = TextureLoader.load_texture(texture_path, self.is_quest_textures)
                    if image:
                        cache_path = TextureLoader.get_cache_path(texture_path)
                        try:
                            image.save(cache_path)
                        except Exception as e:
                            print(f"Failed to cache texture: {e}")
                except Exception as e:
                    print(f"Error loading texture {texture_path}: {e}")
            
            threading.Thread(target=load_texture_thread, daemon=True).start()
        
        self.current_batch_index += batch_size
        self.root.after(5000, self.load_next_batch)

def main():
    root = tk.Tk()
    app = EchoVRTextureViewer(root)
    root.mainloop()

if __name__ == '__main__':
    main()
