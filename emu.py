import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import struct
import numpy as np
import os
import time

class N64Memory:
    def __init__(self):
        self.rdram = bytearray(8 * 1024 * 1024)  # 8MB RDRAM (expandable)
        self.rom = None
        self.sram = bytearray(256 * 1024)  # 256KB SRAM
        self.registers = {}
        
    def load_rom(self, rom_data):
        self.rom = rom_data
        
    def read32(self, address):
        # Memory mapping
        if 0x00000000 <= address < 0x00800000:  # RDRAM
            idx = address & 0x7FFFFF
            return struct.unpack('>I', self.rdram[idx:idx+4])[0]
        elif 0x10000000 <= address < 0x1FC00000:  # ROM
            if self.rom:
                idx = address - 0x10000000
                if idx + 4 <= len(self.rom):
                    return struct.unpack('>I', self.rom[idx:idx+4])[0]
        return 0
        
    def write32(self, address, value):
        if 0x00000000 <= address < 0x00800000:  # RDRAM
            idx = address & 0x7FFFFF
            struct.pack_into('>I', self.rdram, idx, value)

class MIPSR4300i:
    """MIPS R4300i CPU emulation"""
    def __init__(self, memory):
        self.memory = memory
        self.pc = 0xA4000040  # Boot vector
        self.regs = [0] * 32  # General purpose registers
        self.regs[0] = 0  # $zero always 0
        self.hi = 0
        self.lo = 0
        self.cp0_regs = [0] * 32  # Coprocessor 0 registers
        self.cycles = 0
        
    def fetch(self):
        return self.memory.read32(self.pc)
        
    def execute(self):
        instruction = self.fetch()
        opcode = (instruction >> 26) & 0x3F
        
        # Simplified instruction execution
        if opcode == 0x00:  # R-type
            funct = instruction & 0x3F
            rs = (instruction >> 21) & 0x1F
            rt = (instruction >> 16) & 0x1F
            rd = (instruction >> 11) & 0x1F
            
            if funct == 0x20:  # ADD
                self.regs[rd] = (self.regs[rs] + self.regs[rt]) & 0xFFFFFFFF
            elif funct == 0x00:  # SLL
                sa = (instruction >> 6) & 0x1F
                self.regs[rd] = (self.regs[rt] << sa) & 0xFFFFFFFF
                
        elif opcode == 0x08:  # ADDI
            rs = (instruction >> 21) & 0x1F
            rt = (instruction >> 16) & 0x1F
            imm = instruction & 0xFFFF
            if imm & 0x8000:  # Sign extend
                imm |= 0xFFFF0000
            self.regs[rt] = (self.regs[rs] + imm) & 0xFFFFFFFF
            
        elif opcode == 0x23:  # LW
            rs = (instruction >> 21) & 0x1F
            rt = (instruction >> 16) & 0x1F
            offset = instruction & 0xFFFF
            if offset & 0x8000:
                offset |= 0xFFFF0000
            addr = (self.regs[rs] + offset) & 0xFFFFFFFF
            self.regs[rt] = self.memory.read32(addr)
            
        self.pc += 4
        self.cycles += 1
        self.regs[0] = 0  # Keep $zero at 0

class RCP:
    """Reality Coprocessor (RSP + RDP)"""
    def __init__(self):
        self.framebuffer = np.zeros((240, 320, 3), dtype=np.uint8)
        self.vi_regs = {
            'status': 0,
            'origin': 0,
            'width': 320,
            'v_sync': 0,
            'h_sync': 0,
            'leap': 0,
            'h_start': 0,
            'v_start': 0,
            'v_burst': 0,
            'x_scale': 0x200,
            'y_scale': 0x200,
        }
        
    def render_frame(self):
        # Simple test pattern for now
        self.framebuffer[:, :, 0] = 64  # Dark blue background
        self.framebuffer[:, :, 1] = 32
        self.framebuffer[:, :, 2] = 128
        return self.framebuffer

class N64Emulator:
    def __init__(self, root):
        self.root = root
        self.root.title("Project64 - Nintendo 64 Emulator")
        self.root.geometry("800x600")
        
        # Set dark theme
        self.root.configure(bg='#2b2b2b')
        
        self.memory = N64Memory()
        self.cpu = MIPSR4300i(self.memory)
        self.rcp = RCP()
        
        self.rom_loaded = False
        self.running = False
        self.fps = 0
        self.last_frame_time = time.time()
        
        self.setup_gui()
        
    def setup_gui(self):
        # Menu bar
        menubar = tk.Menu(self.root, bg='#3c3c3c', fg='white')
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg='#3c3c3c', fg='white')
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open ROM...", command=self.load_rom, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # System menu
        system_menu = tk.Menu(menubar, tearoff=0, bg='#3c3c3c', fg='white')
        menubar.add_cascade(label="System", menu=system_menu)
        system_menu.add_command(label="Start", command=self.start_emulation, accelerator="F5")
        system_menu.add_command(label="Pause", command=self.pause_emulation, accelerator="F6")
        system_menu.add_command(label="Reset", command=self.reset_emulation, accelerator="F8")
        
        # Options menu
        options_menu = tk.Menu(menubar, tearoff=0, bg='#3c3c3c', fg='white')
        menubar.add_cascade(label="Options", menu=options_menu)
        options_menu.add_command(label="Configure Graphics...")
        options_menu.add_command(label="Configure Audio...")
        options_menu.add_command(label="Configure Controller...")
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0, bg='#3c3c3c', fg='white')
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        
        # Toolbar
        toolbar = tk.Frame(self.root, bg='#3c3c3c', height=40)
        toolbar.pack(fill=tk.X)
        
        # Toolbar buttons
        button_style = {'bg': '#4a4a4a', 'fg': 'white', 'bd': 1, 'relief': tk.RAISED, 'padx': 10}
        
        tk.Button(toolbar, text="📁 Open", command=self.load_rom, **button_style).pack(side=tk.LEFT, padx=2, pady=5)
        tk.Button(toolbar, text="▶ Start", command=self.start_emulation, **button_style).pack(side=tk.LEFT, padx=2, pady=5)
        tk.Button(toolbar, text="⏸ Pause", command=self.pause_emulation, **button_style).pack(side=tk.LEFT, padx=2, pady=5)
        tk.Button(toolbar, text="⏹ Stop", command=self.stop_emulation, **button_style).pack(side=tk.LEFT, padx=2, pady=5)
        tk.Button(toolbar, text="🔄 Reset", command=self.reset_emulation, **button_style).pack(side=tk.LEFT, padx=2, pady=5)
        
        # Main display area
        self.display_frame = tk.Frame(self.root, bg='black')
        self.display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Canvas for rendering
        self.canvas = tk.Canvas(self.display_frame, width=640, height=480, bg='black', highlightthickness=0)
        self.canvas.pack(expand=True)
        
        # Status bar
        self.status_bar = tk.Frame(self.root, bg='#2b2b2b', height=25)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.status_label = tk.Label(self.status_bar, text="Ready", bg='#2b2b2b', fg='white', anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        self.fps_label = tk.Label(self.status_bar, text="FPS: 0", bg='#2b2b2b', fg='white', anchor=tk.E)
        self.fps_label.pack(side=tk.RIGHT, padx=5)
        
        # Initialize display
        self.image = Image.new("RGB", (320, 240))
        self.tk_image = ImageTk.PhotoImage(self.image)
        self.canvas_image = self.canvas.create_image(320, 240, image=self.tk_image)
        
        # Bind keyboard shortcuts
        self.root.bind('<Control-o>', lambda e: self.load_rom())
        self.root.bind('<F5>', lambda e: self.start_emulation())
        self.root.bind('<F6>', lambda e: self.pause_emulation())
        self.root.bind('<F8>', lambda e: self.reset_emulation())
        
    def load_rom(self):
        filename = filedialog.askopenfilename(
            title="Select N64 ROM",
            filetypes=[("N64 ROMs", "*.z64 *.n64 *.v64"), ("All Files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'rb') as f:
                    rom_data = f.read()
                
                # Detect ROM format and endianness
                header = rom_data[:4]
                if header == b'\x80\x37\x12\x40':  # .z64 (big endian)
                    pass
                elif header == b'\x37\x80\x40\x12':  # .n64 (little endian)
                    # Convert to big endian
                    rom_data = self.swap_endian(rom_data)
                elif header == b'\x40\x12\x37\x80':  # .v64 (byte swapped)
                    rom_data = self.byte_swap(rom_data)
                
                self.memory.load_rom(rom_data)
                self.rom_loaded = True
                
                # Extract ROM info
                rom_name = rom_data[0x20:0x34].decode('ascii', errors='ignore').strip()
                self.status_label.config(text=f"Loaded: {rom_name}")
                self.root.title(f"Project64 - {rom_name}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load ROM: {str(e)}")
    
    def swap_endian(self, data):
        # Convert little endian to big endian
        result = bytearray(len(data))
        for i in range(0, len(data), 4):
            result[i:i+4] = data[i:i+4][::-1]
        return bytes(result)
    
    def byte_swap(self, data):
        # Byte swap for .v64 format
        result = bytearray(len(data))
        for i in range(0, len(data), 2):
            result[i] = data[i+1]
            result[i+1] = data[i]
        return bytes(result)
    
    def start_emulation(self):
        if not self.rom_loaded:
            messagebox.showwarning("Warning", "Please load a ROM first!")
            return
            
        self.running = True
        self.status_label.config(text="Running")
        self.emulation_loop()
    
    def pause_emulation(self):
        self.running = False
        self.status_label.config(text="Paused")
    
    def stop_emulation(self):
        self.running = False
        self.reset_emulation()
        self.status_label.config(text="Stopped")
    
    def reset_emulation(self):
        self.cpu = MIPSR4300i(self.memory)
        self.rcp = RCP()
        if self.rom_loaded:
            self.status_label.config(text="Reset")
    
    def emulation_loop(self):
        if not self.running:
            return
            
        # Execute CPU cycles
        for _ in range(1000):  # Execute 1000 instructions per frame
            self.cpu.execute()
        
        # Render frame
        frame = self.rcp.render_frame()
        
        # Update display
        self.image = Image.fromarray(frame, 'RGB')
        self.image = self.image.resize((640, 480), Image.NEAREST)
        self.tk_image = ImageTk.PhotoImage(self.image)
        self.canvas.itemconfig(self.canvas_image, image=self.tk_image)
        
        # Calculate FPS
        current_time = time.time()
        self.fps = 1.0 / (current_time - self.last_frame_time)
        self.last_frame_time = current_time
        self.fps_label.config(text=f"FPS: {self.fps:.1f}")
        
        # Schedule next frame
        self.root.after(16, self.emulation_loop)  # ~60 FPS
    
    def show_about(self):
        messagebox.showinfo("About", 
            "Project64 Style N64 Emulator\n\n"
            "A Nintendo 64 emulator built with Python and Tkinter\n"
            "Version 1.0\n\n"
            "This is a simplified educational implementation")

if __name__ == "__main__":
    root = tk.Tk()
    emulator = N64Emulator(root)
    root.mainloop()
