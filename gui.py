import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import json
import os

# Import the processing engine from your existing code
from transformer import (
    extract_ats_json,
    extract_recruiter_csv,
    extract_notes_txt,
    extract_github_api,
    build_canonical_profile,
    project_profile
)

class TransformerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Multi-Source Candidate Data Transformer")
        self.root.geometry("700x650")
        
        self.files = {
            "ats": "input_ats.json",
            "csv": "input_recruiter.csv",
            "notes": "input_notes.txt",
            "github": "input_github.json",
            "config": "config.json"
        }
        
        self.create_widgets()

    def create_widgets(self):
        # File Selection Frame (FIXED: Changed padding to padx/pady)
        frame_files = tk.LabelFrame(self.root, text=" Input & Configuration Files ", padx=10, pady=10)
        frame_files.pack(fill="x", padx=15, pady=10)

        for idx, (file_key, default_val) in enumerate(self.files.items()):
            lbl = tk.Label(frame_files, text=f"{file_key.upper()} File:", width=12, anchor="w")
            lbl.grid(row=idx, column=0, pady=5, sticky="w")
            
            ent = tk.Entry(frame_files, width=50)
            ent.insert(0, default_val)
            ent.grid(row=idx, column=1, pady=5, padx=5)
            setattr(self, f"entry_{file_key}", ent)
            
            btn = tk.Button(frame_files, text="Browse", command=lambda k=file_key: self.browse_file(k))
            btn.grid(row=idx, column=2, pady=5)

        # ---------------- Output Schema Selection ----------------
        self.output_type = tk.StringVar(value="custom")

        frame_option = tk.LabelFrame(
            self.root,
            text=" Output Schema ",
            padx=10,
            pady=5
        )
        frame_option.pack(fill="x", padx=15, pady=5)

        tk.Radiobutton(
            frame_option,
            text="Default Canonical Schema",
            variable=self.output_type,
            value="default"
        ).pack(side="left", padx=10)

        tk.Radiobutton(
            frame_option,
            text="Custom Config Schema",
            variable=self.output_type,
            value="custom"
        ).pack(side="left", padx=10)

        # ---------------- Run Button ----------------
        btn_run = tk.Button(
            self.root,
            text="⚡ Run Transformation Pipeline",
            font=("Arial", 11, "bold"),
            bg="#4CAF50",
            fg="white",
            padx=10,
            pady=5,
            command=self.run_pipeline
        )
        btn_run.pack(pady=10)

        # Output Frame (FIXED: Changed padding to padx/pady)
        frame_out = tk.LabelFrame(self.root, text=" Projected Canonical Output (JSON) ", padx=10, pady=10)
        frame_out.pack(fill="both", expand=True, padx=15, pady=10)
        
        self.output_area = scrolledtext.ScrolledText(frame_out, wrap=tk.WORD, font=("Courier New", 10))
        self.output_area.pack(fill="both", expand=True)

    def browse_file(self, key):
        file_path = filedialog.askopenfilename()
        if file_path:
            entry = getattr(self, f"entry_{key}")
            entry.delete(0, tk.END)
            entry.insert(0, file_path)

    def run_pipeline(self):
        self.output_area.delete('1.0', tk.END)
        raw_data = []
        
        # Gather paths from inputs
        ats_path = getattr(self, "entry_ats").get()
        csv_path = getattr(self, "entry_csv").get()
        notes_path = getattr(self, "entry_notes").get()
        github_path = getattr(self, "entry_github").get()
        config_path = getattr(self, "entry_config").get()

        # Ingest files if they exist
        if os.path.exists(ats_path): raw_data.extend(extract_ats_json(ats_path))
        if os.path.exists(csv_path): raw_data.extend(extract_recruiter_csv(csv_path))
        if os.path.exists(notes_path): raw_data.extend(extract_notes_txt(notes_path))
        if os.path.exists(github_path): raw_data.extend(extract_github_api(github_path))
        
        if not raw_data:
            messagebox.showerror("Error", "No valid source input files found or processed.")
            return

        if not os.path.exists(config_path):
            messagebox.showerror("Error", f"Configuration file not found at: {config_path}")
            return

        # Core transformation execution
        canonical = build_canonical_profile(raw_data)

        # ---------------- DEFAULT OUTPUT ----------------
        if self.output_type.get() == "default":

            with open("output_default.json", "w") as f:
                json.dump(canonical, f, indent=2)

            self.output_area.insert(
                tk.END,
                json.dumps(canonical, indent=2)
            )

        # ---------------- CUSTOM OUTPUT ----------------
        else:

            with open(config_path, "r") as f:
                runtime_config = json.load(f)

            try:
                final_output = project_profile(
                    canonical,
                    runtime_config
                )

                with open("output_custom.json", "w") as f:
                    json.dump(final_output, f, indent=2)

                self.output_area.insert(
                    tk.END,
                    json.dumps(final_output, indent=2)
                )

            except ValueError as e:
                self.output_area.insert(
                    tk.END,
                    json.dumps({"error": str(e)}, indent=2)
                )

if __name__ == "__main__":
    root = tk.Tk()
    app = TransformerGUI(root)
    root.mainloop()