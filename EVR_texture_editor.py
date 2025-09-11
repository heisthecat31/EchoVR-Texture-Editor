import os
import sys
import struct
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from PIL import Image, ImageTk, ImageDraw # type: ignore
import shutil
import tempfile
import subprocess
import threading
import json
import glob
import time

CONFIG_FILE = "config.json"

class ConfigManager:
    
    @staticmethod
    def load_config():
        config = {
            'output_folder': None,
            'input_folder': None,
            'renderdoc_path': None,
            'data_folder': None,
            'extracted_folder': None
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
    def save_config(output_folder=None, input_folder=None, renderdoc_path=None, data_folder=None, extracted_folder=None):
        config = ConfigManager.load_config()
        
        if output_folder is not None:
            config['output_folder'] = output_folder
        if input_folder is not None:
            config['input_folder'] = input_folder
        if renderdoc_path is not None:
            config['renderdoc_path'] = renderdoc_path
        if data_folder is not None:
            config['data_folder'] = data_folder
        if extracted_folder is not None:
            config['extracted_folder'] = extracted_folder
        
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            print(f"Config save error: {e}")

class EVRToolsManager:
    
    def __init__(self):
        self.tool_path = self.find_tool()
        print(f"Found tool: {self.tool_path}")
        
    def find_tool(self):
        """Find the echoModifyFiles.exe tool"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths = [
            os.path.join(script_dir, "echoModifyFiles.exe"),
            os.path.join(script_dir, "evrFileTools.exe"),
            os.path.join(script_dir, "echoFileTools.exe"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    def extract_package(self, data_dir, package_name, output_dir):
        """Extract package using echoModifyFiles.exe"""
        if not self.tool_path:
            return False, "echoModifyFiles.exe not found. Place it in script directory."
        
        try:
            cmd = [
                self.tool_path,
                "-mode", "extract",
                "-packageName", package_name,
                "-dataDir", data_dir,
                "-outputFolder", output_dir
            ]
            
            print(f"Running extraction: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  cwd=os.path.dirname(self.tool_path), timeout=600)
            
            if result.returncode == 0:
                return True, f"Extracted to {output_dir}"
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                return False, f"Extraction failed: {error_msg}"
                
        except subprocess.TimeoutExpired:
            return False, "Extraction timed out after 10 minutes"
        except Exception as e:
            return False, f"Extraction error: {str(e)}"
    
    def repack_package(self, output_dir, package_name, data_dir, modified_folder):
        """Repack modified files using echoModifyFiles.exe with new command format"""
        if not self.tool_path:
            return False, "echoModifyFiles.exe not found. Place it in script directory."
        
        try:
            cmd = [
                self.tool_path,
                "-mode", "replace",
                "-packageName", package_name,
                "-dataDir", data_dir,
                "-modifiedFolder", modified_folder,
                "-outputFolder", output_dir
            ]
            
            print(f"Running repacking: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, 
                                  cwd=os.path.dirname(self.tool_path), timeout=300)
            
            if result.returncode == 0:
                return True, f"Repacked successfully to {output_dir}"
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                return False, f"Repacking failed: {error_msg}"
                
        except subprocess.TimeoutExpired:
            return False, "Repacking timed out after 5 minutes"
        except Exception as e:
            return False, f"Repacking error: {str(e)}"

class DDSHandler:
    
    DXGI_FORMAT = {
        28: "DXGI_FORMAT_R8G8B8A8_UNORM",
        71: "DXGI_FORMAT_BC1_UNORM",
        74: "DXGI_FORMAT_BC2_UNORM",
        77: "DXGI_FORMAT_BC3_UNORM",
        87: "DXGI_FORMAT_B8G8R8A8_UNORM",
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
                if four_cc == b'DXT1':
                    format_name = "BC1/DXT1"
                elif four_cc == b'DXT3':
                    format_name = "BC2/DXT3"
                elif four_cc == b'DXT5':
                    format_name = "BC3/DXT5"
                elif four_cc == b'DX10':
                    extended_header = f.read(20)
                    if len(extended_header) >= 20:
                        dxgi_format = struct.unpack('<I', extended_header[0:4])[0]
                        format_name = DDSHandler.DXGI_FORMAT.get(dxgi_format, f"DXGI Format {dxgi_format}")
                elif pixel_format_flags & 0x40:
                    format_name = "RGB"
                
                return {
                    'width': width,
                    'height': height,
                    'mipmaps': mipmap_count,
                    'format': format_name,
                    'file_size': os.path.getsize(file_path)
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
    
    @staticmethod
    def load_texture(dds_path):
        try:
            dds_info = DDSHandler.get_dds_info(dds_path)
            
            if not dds_info:
                return DDSHandler.create_format_preview(256, 256, "Invalid DDS", dds_path)
            
            try:
                img = Image.open(dds_path)
                if img:
                    return img
            except:
                pass
            
            return TextureLoader.create_texture_preview(dds_info, dds_path)
                    
        except Exception:
            return DDSHandler.create_format_preview(256, 256, "Error Loading", dds_path)
    
    @staticmethod
    def create_texture_preview(dds_info, file_path):
        width = dds_info['width']
        height = dds_info['height']
        format_name = dds_info['format']
        
        img = Image.new('RGB', (max(256, width), max(256, height)), '#1a1a3a')
        draw = ImageDraw.Draw(img)
        
        grid_size = max(1, min(32, width // 8, height // 8))
        for x in range(0, img.width, grid_size):
            draw.line([(x, 0), (x, img.height)], fill='#2a2a5a', width=1)
        for y in range(0, img.height, grid_size):
            draw.line([(0, y), (img.width, y)], fill='#2a2a5a', width=1)
        
        if any(f in format_name for f in ['BC', 'DXT', 'DXGI']):
            TextureLoader.draw_compression_pattern(draw, width, height)
        elif 'RGB' in format_name:
            TextureLoader.draw_rgb_pattern(draw, width, height)
        else:
            TextureLoader.draw_generic_pattern(draw, width, height)
        
        y_pos = 20
        draw.text((20, y_pos), f"Format: {format_name}", fill='#00a8ff')
        y_pos += 25
        draw.text((20, y_pos), f"Size: {width}x{height}", fill='#ffffff')
        y_pos += 25
        draw.text((20, y_pos), f"File: {os.path.basename(file_path)}", fill='#b8b8d9')
        
        return img
    
    @staticmethod
    def draw_compression_pattern(draw, width, height):
        block_size = 16
        colors = ['#ff6b6b', '#4cd964', '#00a8ff', '#9d4edd']
        
        for y in range(0, height, block_size):
            for x in range(0, width, block_size):
                color = colors[(x // block_size + y // block_size) % len(colors)]
                draw.rectangle([x, y, x + block_size - 2, y + block_size - 2], fill=color)
    
    @staticmethod
    def draw_rgb_pattern(draw, width, height):
        tile_size = 24
        colors = ['#ff6b6b', '#4cd964', '#00a8ff']
        
        for y in range(0, height, tile_size):
            for x in range(0, width, tile_size):
                color = colors[(x // tile_size) % len(colors)]
                draw.rectangle([x, y, x + tile_size - 2, y + tile_size - 2], fill=color)
    
    @staticmethod
    def draw_generic_pattern(draw, width, height):
        tile_size = 20
        colors = ['#ff6b6b', '#4cd964', '#00a8ff', '#9d4edd', '#ff9f43']
        
        for y in range(0, height, tile_size):
            for x in range(0, width, tile_size):
                color = colors[(x // tile_size + y // tile_size) % len(colors)]
                draw.rectangle([x, y, x + tile_size - 2, y + tile_size - 2], fill=color)

class TextureReplacer:
    
    @staticmethod
    def hex_edit_file_size(file_path, new_size):
        try:
            with open(file_path, 'r+b') as f:
                data = bytearray(f.read())
                
                if len(data) != 256:
                    return False
                
                file_size_bytes = struct.pack('<I', new_size)
                data[244:248] = file_size_bytes
                
                f.seek(0)
                f.write(data)
                f.truncate()
                
                return True
                
        except Exception:
         return False
    
    @staticmethod
    def replace_texture(output_folder, input_folder, original_texture_path, replacement_texture_path, replacement_size):
        try:
            input_textures_folder = os.path.join(input_folder, "-4707359568332879775")
            input_corresponding_folder = os.path.join(input_folder, "5353709876897953952")
            
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
                    return True, f"Texture replaced. Size updated to {replacement_size} bytes."
                else:
                    return False, "Failed to update file size"
            else:
                return False, "Corresponding file not found"
                
        except Exception as e:
            return False, f"Replacement error: {str(e)}"

class RenderDocManager:
    
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
        self.root.title("EchoVR Texture Editor")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)
        
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
        self.renderdoc_path = self.config.get('renderdoc_path')
        
        self.evr_tools = EVRToolsManager()
        self.data_folder = self.config.get('data_folder')
        self.extracted_folder = self.config.get('extracted_folder')
        self.package_name = None
        
        self.textures_folder = None
        self.corresponding_folder = None
        self.current_texture = None
        self.replacement_texture = None
        self.original_info = None
        self.replacement_info = None
        self.replacement_size = None
        
        self.setup_ui()
        
        if self.output_folder and os.path.exists(self.output_folder):
            self.set_output_folder(self.output_folder)
        
        if self.input_folder and os.path.exists(self.input_folder):
            self.set_input_folder(self.input_folder)
            
        if self.data_folder and os.path.exists(self.data_folder):
            self.set_data_folder(self.data_folder)
            
        if self.extracted_folder and os.path.exists(self.extracted_folder):
            self.set_extracted_folder(self.extracted_folder)
        
    def setup_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.grid(row=0, column=0, sticky='nsew')
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        header_frame = ttk.Frame(main_frame)
        header_frame.grid(row=0, column=0, columnspan=3, sticky='ew', pady=(0, 5))
        header_frame.columnconfigure(0, weight=1)
        
        title_label = tk.Label(header_frame, text="ECHO VR TEXTURE EDITOR", 
                              font=('Arial', 14, 'bold'), 
                              fg=self.colors['accent_blue'],
                              bg=self.colors['bg_dark'])
        title_label.grid(row=0, column=0, sticky='w')
        
        self.output_folder_button = tk.Button(header_frame, text="Select Output Folder", 
                                            command=self.select_output_folder,
                                            bg=self.colors['accent_blue'],
                                            fg=self.colors['text_light'],
                                            font=('Arial', 9, 'bold'))
        self.output_folder_button.grid(row=0, column=1, sticky='e', padx=5)
        
        self.input_folder_button = tk.Button(header_frame, text="Select Input Folder", 
                                           command=self.select_input_folder,
                                           bg=self.colors['accent_purple'],
                                           fg=self.colors['text_light'],
                                           font=('Arial', 9, 'bold'))
        self.input_folder_button.grid(row=0, column=2, sticky='e', padx=5)
        
        self.status_label = tk.Label(main_frame, text="No folders selected",
                                   fg=self.colors['text_muted'], bg=self.colors['bg_dark'],
                                   font=('Arial', 9))
        self.status_label.grid(row=1, column=0, columnspan=3, sticky='ew', pady=(0, 5))
        
        evr_frame = ttk.LabelFrame(main_frame, text="EVR TOOLS INTEGRATION", padding=5)
        evr_frame.grid(row=2, column=0, columnspan=3, sticky='ew', pady=(0, 5))
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
        
        # Show tool status
        tool_status = "Tool: "
        if self.evr_tools.tool_path:
            tool_status += f"{os.path.basename(self.evr_tools.tool_path)} ✓"
        else:
            tool_status += "Not found ✗"
            
        self.evr_status_label = ttk.Label(evr_frame, text=tool_status, foreground=self.colors['text_muted'])
        self.evr_status_label.grid(row=4, column=0, columnspan=3, pady=2)
        
        left_frame = ttk.LabelFrame(main_frame, text="AVAILABLE TEXTURES", padding=5)
        left_frame.grid(row=3, column=0, sticky='nsew', padx=(0, 5))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=1)
        
        list_frame = ttk.Frame(left_frame)
        list_frame.grid(row=0, column=0, sticky='nsew')
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
        middle_frame.grid(row=3, column=1, sticky='nsew', padx=5)
        middle_frame.columnconfigure(0, weight=1)
        middle_frame.rowconfigure(0, weight=1)
        
        self.original_canvas = tk.Canvas(middle_frame, bg=self.colors['bg_medium'])
        self.original_canvas.grid(row=0, column=0, sticky='nsew')
        
        right_frame = ttk.LabelFrame(main_frame, text="REPLACEMENT TEXTURE", padding=5)
        right_frame.grid(row=3, column=2, sticky='nsew', padx=(5, 0))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        
        self.replacement_canvas = tk.Canvas(right_frame, bg=self.colors['bg_medium'])
        self.replacement_canvas.grid(row=0, column=0, sticky='nsew')
        self.replacement_canvas.bind("<Button-1>", self.browse_replacement_texture)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, sticky='ew', pady=(10, 0))
        
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
        
        self.resolution_status = tk.Label(button_frame, text="",
                                        fg=self.colors['text_muted'], bg=self.colors['bg_dark'],
                                        font=('Arial', 9))
        self.resolution_status.pack(side=tk.LEFT, padx=10)
        
        info_frame = ttk.LabelFrame(main_frame, text="TEXTURE INFORMATION", padding=5)
        info_frame.grid(row=5, column=0, columnspan=3, sticky='nsew', pady=(10, 0))
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
        main_frame.rowconfigure(3, weight=3)
        main_frame.rowconfigure(5, weight=1)
        
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
        
    def select_output_folder(self):
        path = filedialog.askdirectory(title="Select Output Folder (contains original textures)")
        if path:
            self.set_output_folder(path)
            
    def set_output_folder(self, path):
        self.output_folder = path
        self.textures_folder = os.path.join(path, "-4707359568332879775")
        self.corresponding_folder = os.path.join(path, "5353709876897953952")
        
        if os.path.exists(self.textures_folder):
            self.status_label.config(text=f"Output folder: {os.path.basename(path)}")
            self.log_info(f"Output folder set: {path}")
            self.load_textures()
            ConfigManager.save_config(output_folder=self.output_folder)
        else:
            messagebox.showerror("Error", "Textures folder not found! Make sure the output folder contains:\n-4707359568332879775")
            
    def select_input_folder(self):
        path = filedialog.askdirectory(title="Select Input Folder (where modified textures go)")
        if path:
            self.set_input_folder(path)
            
    def set_input_folder(self, path):
        self.input_folder = path
        self.status_label.config(text=f"Input folder: {os.path.basename(path)}")
        self.log_info(f"Input folder set: {path}")
        ConfigManager.save_config(input_folder=self.input_folder)
            
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
            
            # Try to find the extracted textures folder
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
            os.path.join(base_dir, "**", "textures"),
        ]
        
        for pattern in texture_patterns:
            for path in glob.glob(pattern, recursive=True):
                if os.path.isdir(path):
                    return os.path.dirname(path)  # Return the parent directory
        
        return None
    
    def repack_package(self):
        if not all([self.data_folder, self.package_name, self.extracted_folder, self.input_folder]):
            messagebox.showerror("Error", "Please select data folder, package, extraction folder, and input folder first.")
            return
        
        output_dir = filedialog.askdirectory(title="Select Output Directory for Repacked Package")
        if not output_dir:
            return
        
        self.evr_status_label.config(text="Repacking package...", foreground=self.colors['accent_blue'])
        self.root.update_idletasks()
        
        def repacking_thread():
            success, message = self.evr_tools.repack_package(
                output_dir, 
                self.package_name, 
                self.data_folder, 
                self.input_folder  # Using input_folder as modifiedFolder
            )
            
            self.root.after(0, lambda: self.on_repacking_complete(success, message, output_dir))
        
        threading.Thread(target=repacking_thread, daemon=True).start()
    
    def on_repacking_complete(self, success, message, output_dir):
        if success:
            self.evr_status_label.config(text="Repacking successful!", foreground=self.colors['success'])
            self.log_info(f"✓ REPACKING: {message}")
            
            # Just log where the files are, don't move them
            packages_path = os.path.join(output_dir, "packages")
            manifests_path = os.path.join(output_dir, "manifests")
            
            if os.path.exists(packages_path) and os.path.exists(manifests_path):
                self.log_info(f"✓ Packages and manifests created in: {output_dir}")
            else:
                self.log_info("⚠ Packages or manifests folders not found in output directory")
            
        else:
            self.evr_status_label.config(text="Repacking failed", foreground=self.colors['error'])
            self.log_info(f"✗ REPACKING FAILED: {message}")
        
        messagebox.showinfo("Repacking Result", message)
    
    def move_repacked_files(self, output_dir):
        """Move the repacked packages and manifests folders to their final location"""
        try:
            # Look for packages and manifests folders in the output directory
            packages_src = os.path.join(output_dir, "packages")
            manifests_src = os.path.join(output_dir, "manifests")
            
            if os.path.exists(packages_src) and os.path.exists(manifests_src):
                # Create the final destination directory if it doesn't exist
                final_dest = self.extracted_folder
                os.makedirs(final_dest, exist_ok=True)
                
                # Move packages folder
                packages_dest = os.path.join(final_dest, "packages")
                if os.path.exists(packages_dest):
                    shutil.rmtree(packages_dest)
                shutil.move(packages_src, final_dest)
                
                # Move manifests folder
                manifests_dest = os.path.join(final_dest, "manifests")
                if os.path.exists(manifests_dest):
                    shutil.rmtree(manifests_dest)
                shutil.move(manifests_src, final_dest)
                
                self.log_info(f"✓ Moved repacked files to: {final_dest}")
            else:
                self.log_info("⚠ Packages or manifests folders not found in output directory")
                
        except Exception as e:
            self.log_info(f"✗ Error moving repacked files: {e}")
    
    def load_textures(self):
        self.file_list.delete(0, tk.END)
        self.file_list.insert(tk.END, "Loading textures...")
        self.update_canvas_placeholder(self.original_canvas, "Loading textures...")
        self.root.update_idletasks()
        
        try:
            texture_count = 0
            dds_files = []
            
            if not os.path.exists(self.textures_folder):
                self.log_info("Textures folder not found!")
                return
                
            for file_name in os.listdir(self.textures_folder):
                file_path = os.path.join(self.textures_folder, file_name)
                if os.path.isfile(file_path):
                    try:
                        with open(file_path, 'rb') as f:
                            signature = f.read(4)
                            if signature == b'DDS ':
                                dds_files.append(file_name)
                                texture_count += 1
                    except:
                        if file_name.lower().endswith('.dds'):
                            dds_files.append(file_name)
                            texture_count += 1
                            continue
            
            self.file_list.delete(0, tk.END)
            for file_name in sorted(dds_files):
                self.file_list.insert(tk.END, file_name)
                
            self.log_info(f"Found {texture_count} DDS texture files")
            
            if texture_count == 0:
                self.log_info("No DDS files found.")
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
        texture_name = self.file_list.get(index)
        self.current_texture = os.path.join(self.textures_folder, texture_name)
        
        try:
            self.update_canvas_placeholder(self.original_canvas, "Loading texture...")
            self.root.update_idletasks()
            
            image = self.load_dds(self.current_texture)
            if image:
                self.display_image_on_canvas(image, self.original_canvas)
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
        except Exception as e:
            self.log_info(f"Error loading texture: {e}")
            self.update_canvas_placeholder(self.original_canvas, "Error loading texture")
            
    def browse_replacement_texture(self, event):
        if not self.current_texture:
            messagebox.showinfo("Info", "Please select an original texture first")
            return
            
        file_path = filedialog.askopenfilename(
            title="Select Replacement Texture",
            filetypes=[("DDS files", "*.dds"), ("All files", "*.*")]
        )
        
        if file_path:
            self.replacement_texture = file_path
            try:
                image = self.load_dds(file_path)
                if image:
                    self.display_image_on_canvas(image, self.replacement_canvas)
                    self.replacement_info = DDSHandler.get_dds_info(file_path)
                    self.replacement_size = self.replacement_info['file_size']
                    self.update_texture_info()
                    self.check_resolution_match()
                    self.log_info(f"Replacement loaded: {os.path.basename(file_path)}")
                    self.log_info(f"Replacement size: {self.replacement_size} bytes")
                else:
                    self.update_canvas_placeholder(self.replacement_canvas, "Failed to load replacement")
            except Exception as e:
                self.log_info(f"Error loading replacement texture: {e}")
                self.update_canvas_placeholder(self.replacement_canvas, "Error loading replacement")
    
    def load_dds(self, file_path):
        return TextureLoader.load_texture(file_path)
            
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
            info += "=== ORIGINAL TEXTURE ===\n"
            info += f"File: {os.path.basename(self.current_texture)}\n"
            info += f"Size: {self.original_info['file_size']:,} bytes\n"
            info += f"Dimensions: {self.original_info['width']} x {self.original_info['height']}\n"
            info += f"Format: {self.original_info['format']}\n"
            info += f"Mipmaps: {self.original_info.get('mipmaps', 1)}\n"
            info += "\n"
        
        if self.replacement_info:
            info += "=== REPLACEMENT TEXTURE ===\n"
            info += f"File: {os.path.basename(self.replacement_texture)}\n"
            info += f"Size: {self.replacement_info['file_size']:,} bytes\n"
            info += f"Dimensions: {self.replacement_info['width']} x {self.replacement_info['height']}\n"
            info += f"Format: {self.replacement_info['format']}\n"
            info += f"Mipmaps: {self.replacement_info.get('mipmaps', 1)}\n"
            info += "\n"
        
        if self.original_info and self.replacement_info:
            info += "=== COMPARISON ===\n"
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
            
            if orig_format == rep_format:
                info += f"✓ Format match: {orig_format}\n"
            else:
                info += f"⚠ Format difference: {orig_format} vs {rep_format}\n"
                
            orig_size = self.original_info['file_size']
            rep_size = self.replacement_info['file_size']
            size_diff = rep_size - orig_size
            size_percent = (size_diff / orig_size) * 100 if orig_size > 0 else 0
            
            if abs(size_percent) < 10:
                info += f"✓ Size similar: {orig_size:,} vs {rep_size:,} bytes ({size_percent:+.1f}%)\n"
            else:
                info += f"⚠ Size difference: {orig_size:,} vs {rep_size:,} bytes ({size_percent:+.1f}%)\n"
        
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, info)
            
    def check_resolution_match(self):
        if self.original_info and self.replacement_info:
            orig_width = self.original_info['width']
            orig_height = self.original_info['height']
            rep_width = self.replacement_info['width']
            rep_height = self.replacement_info['height']
            
            if orig_width == rep_width and orig_height == rep_height:
                self.resolution_status.config(
                    text="✓ Resolutions match", 
                    fg=self.colors['success']
                )
                self.replace_button.config(state=tk.NORMAL, bg=self.colors['accent_blue'])
            else:
                self.resolution_status.config(
                    text=f"✗ Resolutions don't match ({orig_width}x{orig_height} vs {rep_width}x{rep_height})", 
                    fg=self.colors['error']
                )
                self.replace_button.config(state=tk.DISABLED, bg='#666666')
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
        if not self.current_texture or not self.replacement_texture or not self.output_folder or not self.input_folder:
            return
            
        if self.original_info and self.replacement_info:
            orig_width = self.original_info['width']
            orig_height = self.original_info['height']
            rep_width = self.replacement_info['width']
            rep_height = self.replacement_info['height']
            
            if orig_width != rep_width or orig_height != rep_height:
                if not messagebox.askyesno("Warning", 
                                          "Resolutions don't match! This may cause issues.\n\n"
                                          f"Original: {orig_width}x{orig_height}\n"
                                          f"Replacement: {rep_width}x{rep_height}\n\n"
                                          "Continue anyway?"):
                    return
        
        if self.replacement_info and 'file_size' in self.replacement_info:
            replacement_size = self.replacement_info['file_size']
            
            success, message = TextureReplacer.replace_texture(
                self.output_folder,
                self.input_folder,
                self.current_texture, 
                self.replacement_texture,
                replacement_size
            )
            
            if success:
                messagebox.showinfo("Success", message)
                self.log_info(f"✓ REPLACEMENT: {message}")
                self.on_texture_selected(None)
            else:
                messagebox.showerror("Error", message)
                self.log_info(f"✗ REPLACEMENT FAILED: {message}")
        else:
            messagebox.showerror("Error", "Could not determine replacement file size")
            self.log_info("✗ Could not determine replacement file size")
            
    def log_info(self, message):
        self.info_text.insert(tk.END, message + "\n")
        self.info_text.see(tk.END)
        self.info_text.update_idletasks()

def main():
    root = tk.Tk()
    app = EchoVRTextureViewer(root)
    root.mainloop()

if __name__ == '__main__':
    main()