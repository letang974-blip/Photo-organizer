import os
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from PIL import Image, ImageTk
import exifread
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

# ----------------------------- #
# Variables globales conflits
# ----------------------------- #
apply_to_all = False
conflict_choice = None

# ----------------------------- #
# Extraction EXIF
# ----------------------------- #
def extract_date(filepath):
    try:
        with open(filepath, 'rb') as f:
            tags = exifread.process_file(f, stop_tag="EXIF DateTimeOriginal", details=False)
            dt = tags.get("EXIF DateTimeOriginal")
            if dt:
                return datetime.strptime(str(dt), "%Y:%m:%d %H:%M:%S")
    except:
        pass
    return None

def extract_gps(filepath):
    try:
        with open(filepath, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            gps_lat = tags.get("GPS GPSLatitude")
            gps_lat_ref = tags.get("GPS GPSLatitudeRef")
            gps_lon = tags.get("GPS GPSLongitude")
            gps_lon_ref = tags.get("GPS GPSLongitudeRef")
            if gps_lat and gps_lat_ref and gps_lon and gps_lon_ref:
                def conv(val):
                    d, m, s = [x.num/x.den for x in val.values]
                    return d + m/60 + s/3600
                lat = conv(gps_lat)
                lon = conv(gps_lon)
                if gps_lat_ref.values[0] != "N": lat = -lat
                if gps_lon_ref.values[0] != "E": lon = -lon
                return round(lat,2), round(lon,2)
    except:
        pass
    return None

# ----------------------------- #
# Distances en kilomètres
# ----------------------------- #
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c

# ----------------------------- #
# Gestion des conflits
# ----------------------------- #
def handle_conflict(src, dst):
    global apply_to_all, conflict_choice

    if apply_to_all and conflict_choice:
        return conflict_choice

    conflict_window = tk.Toplevel()
    conflict_window.title("Conflit de fichier")
    conflict_window.geometry("400x400")

    tk.Label(conflict_window, text=f"Le fichier existe déjà :\n{os.path.basename(dst)}").pack(pady=10)

    try:
        img = Image.open(src)
        img.thumbnail((200,200))
        preview = ImageTk.PhotoImage(img)
        tk.Label(conflict_window, image=preview).pack()
        conflict_window.image = preview
    except:
        tk.Label(conflict_window, text="[Impossible d'afficher l'image]").pack()

    var = tk.StringVar(value="ignorer")
    apply_var = tk.BooleanVar(value=False)

    # Options disponibles : Écraser, Renommer, Ignorer
    for text, val in [("Écraser", "overwrite"), ("Renommer", "unique"), ("Ignorer", "ignorer")]:
        tk.Radiobutton(conflict_window, text=text, variable=var, value=val).pack(anchor="w")

    tk.Checkbutton(conflict_window, text="Appliquer à tous les conflits suivants", variable=apply_var).pack()

    def validate():
        global apply_to_all, conflict_choice  # <-- important !
        choice = var.get()
        if apply_var.get():
            apply_to_all = True
            conflict_choice = choice
        conflict_window.destroy()

    tk.Button(conflict_window, text="Valider", command=validate).pack(pady=10)
    conflict_window.wait_window()
    return var.get()


# ----------------------------- #
# GPS Grouping
# ----------------------------- #
def group_gps_day(locations, threshold_km=2):
    if not locations:
        return []

    groups = [[locations[0]]]
    for loc in locations[1:]:
        last = groups[-1][-1]
        if haversine(loc[0], loc[1], last[0], last[1]) <= threshold_km:
            groups[-1].append(loc)
        else:
            groups.append([loc])
    return [g[0] for g in groups]

# ----------------------------- #
# Tri des images
# ----------------------------- #
def sort_images(src, dst, mode, conflict_mode, copy_mode, advanced):
    global apply_to_all, conflict_choice
    apply_to_all = False
    conflict_choice = None

    threshold_km = advanced.get("threshold", 2.0)
    gps_flag = advanced.get("gps", False)
    files = [f for f in os.listdir(src) if os.path.isfile(os.path.join(src, f))]
    items = []
    problematic = []

    for f in files:
        path = os.path.join(src, f)
        try:
            date = extract_date(path) or datetime.fromtimestamp(os.path.getmtime(path))
            gps = extract_gps(path)
            items.append((path, f, date, gps))
        except:
            problematic.append((f, "Impossible de lire"))
            continue

    day_groups = {}
    for path, f, date, gps in items:
        day_key = date.strftime("%Y-%m-%d")
        if day_key not in day_groups:
            day_groups[day_key] = []
        day_groups[day_key].append((path, f, date, gps))

    total_files = 0
    for path, f, date, gps in items:
        year, month, day = date.strftime("%Y"), date.strftime("%m"), date.strftime("%d")
        base = dst

       # ----------------- MODE CUSTOM -----------------
        if mode == "Custom":
            parts = []
            if advanced.get("year"): parts.append(year)
            if advanced.get("month"):
                if advanced.get("year"): parts.append(month)
                else: parts.append(month)
            if advanced.get("day"):
                if advanced.get("year") and advanced.get("month"):
                    parts.append(day)
                elif advanced.get("year") and not advanced.get("month"):
                    parts.append(f"{month}-{day}")  # année+jour -> 2025/11-02
                elif not advanced.get("year") and advanced.get("month"):
                    parts.append(f"{month}-{day}")  # mois+jour -> 11-02
                else:
                    parts.append(f"{year}-{month}-{day}")  # jour seul -> 2025-11-02

            base = os.path.join(base, *parts)

            # Gestion GPS uniquement si coché
            if gps_flag and gps:
                # Récupère tous les points GPS du jour
                day_gps_points = [g for _, _, _, g in day_groups[date.strftime("%Y-%m-%d")] if g]

                # Détecte clusters selon threshold
                if advanced.get("clustering"):
                    clusters = group_gps_day(day_gps_points, threshold_km)
                else:
                    clusters = []
                    for g_point in day_gps_points:
                        found = None
                        for i, ref in enumerate(clusters):
                            if haversine(g_point[0], g_point[1], ref[0], ref[1]) <= threshold_km:
                                found = i
                                break
                        if found is None:
                            clusters.append(g_point)

                # Ne créer sous-dossier GPS que si plusieurs clusters distincts
                if len(clusters) > 1:
                    if advanced.get("clustering"):
                        best_cluster = min(clusters, key=lambda c: haversine(gps[0], gps[1], c[0], c[1]))
                        gps_name = f"{round(best_cluster[0],2)}_{round(best_cluster[1],2)}"
                    else:
                        found = None
                        for i, ref in enumerate(clusters):
                            if haversine(gps[0], gps[1], ref[0], ref[1]) <= threshold_km:
                                found = i
                                break
                        gps_name = f"{found+1}" if found is not None else "1"
                    base = os.path.join(base, gps_name)
                
        # ----------------- MODE GPS -----------------
        elif mode == "GPS":
            base = os.path.join(dst, year, month, day)
            gps_name = None
            day_gps_points = [g for _, _, _, g in day_groups[date.strftime("%Y-%m-%d")] if g]

            if gps and day_gps_points:
                # Si clustering est activé ou plusieurs points distincts
                if advanced.get("clustering"):
                    clusters = group_gps_day(day_gps_points, threshold_km)
                    if len(clusters) > 1:  # crée un sous-dossier seulement si plusieurs clusters
                        best_cluster = min(clusters, key=lambda c: haversine(gps[0], gps[1], c[0], c[1]))
                        gps_name = f"{round(best_cluster[0],2)}_{round(best_cluster[1],2)}"
                else:
                    # Si plus d'un point distinct
                    distinct_points = []
                    for g_point in day_gps_points:
                        if all(haversine(g_point[0], g_point[1], dp[0], dp[1]) > threshold_km for dp in distinct_points):
                            distinct_points.append(g_point)
                    if len(distinct_points) > 1:
                        idx = next(i+1 for i, dp in enumerate(distinct_points) if haversine(gps[0], gps[1], dp[0], dp[1]) <= threshold_km)
                        gps_name = f"{idx}"

            if gps_name:
                base = os.path.join(base, gps_name)


        # ----------------- MODE JOUR/MOIS/ANNEE -----------------
        else:
            base = os.path.join(dst, year)
            if mode in ["Mois","Jour"]: base = os.path.join(base, month)
            if mode == "Jour": base = os.path.join(base, day)

        os.makedirs(base, exist_ok=True)
        dest = os.path.join(base, f)

        # ----------------- GESTION DES CONFLITS -----------------
        if os.path.exists(dest):
            if conflict_mode == "écraser":
                os.remove(dest)
            elif conflict_mode == "ignorer":
                continue
            elif conflict_mode == "renommer":
                name, ext = os.path.splitext(f)
                i = 1
                while os.path.exists(dest):
                    dest = os.path.join(base, f"{name}_{i}{ext}")
                    i += 1
            elif conflict_mode == "demander":
                choice = handle_conflict(path, dest)
                if choice == "overwrite": os.remove(dest)
                elif choice == "ignorer": continue
                elif choice == "unique":
                    name, ext = os.path.splitext(f)
                    i = 1
                    while os.path.exists(dest):
                        dest = os.path.join(base, f"{name}_{i}{ext}")
                        i += 1

        # ----------------- COPIE OU DEPLACEMENT -----------------
        if copy_mode == "copier":
            shutil.copy2(path, dest)
        else:
            shutil.move(path, dest)

        total_files += 1

    # ----------------- RAPPORT FINAL -----------------
    report_window = tk.Toplevel()
    report_window.title("Tri terminé")
    tk.Label(report_window, text=f"Nombre de fichiers traités : {total_files}").pack(pady=5)

    # Bloc détaillé caché
    details_frame = tk.Frame(report_window)
    details_frame.pack(fill="both", expand=True)
    details_frame.pack_forget()

    tk.Button(report_window, text="Détails ▼", command=lambda: toggle_details(details_frame)).pack(pady=5)

    def toggle_details(frame):
        if frame.winfo_ismapped():
            frame.pack_forget()
        else:
            frame.pack(fill="both", expand=True)

    tk.Label(details_frame, text="Problèmes rencontrés :").pack()
    listbox = tk.Listbox(details_frame, width=80)
    listbox.pack()
    for f, reason in problematic:
        listbox.insert(tk.END, f"{f} : {reason}")

# ----------------------------- #
# GUI
# ----------------------------- #
def build_gui():
    root=tk.Tk()
    root.title("Photo Organizer")

    # Dossier source
    tk.Label(root,text="Dossier source").grid(row=0,column=0,sticky="w")
    src_entry=tk.Entry(root,width=50)
    src_entry.grid(row=0,column=1)
    tk.Button(root,text="Parcourir",command=lambda: src_entry.insert(0,filedialog.askdirectory())).grid(row=0,column=2)

    # Dossier destination
    tk.Label(root,text="Dossier destination").grid(row=1,column=0,sticky="w")
    dst_entry=tk.Entry(root,width=50)
    dst_entry.grid(row=1,column=1)
    tk.Button(root,text="Parcourir",command=lambda: dst_entry.insert(0,filedialog.askdirectory())).grid(row=1,column=2)

    # Mode de tri
    tk.Label(root,text="Mode de tri").grid(row=2,column=0,sticky="w")
    sort_cb=ttk.Combobox(root,values=["Jour","Mois","Année","GPS","Custom"])
    sort_cb.set("Jour")
    sort_cb.grid(row=2,column=1)

    # Copie ou déplacement
    tk.Label(root,text="Action").grid(row=3,column=0,sticky="w")
    copy_cb=ttk.Combobox(root,values=["copier","deplacer"])
    copy_cb.set("copier")
    copy_cb.grid(row=3,column=1)

    # Conflits
    tk.Label(root,text="Conflits").grid(row=4,column=0,sticky="w")
    conflict_cb=ttk.Combobox(root,values=["demander","ignorer","renommer","écraser"])
    conflict_cb.set("demander")
    conflict_cb.grid(row=4,column=1)

    # Options avancées masquées
    adv_frame=tk.Frame(root)
    adv_frame.grid(row=6,column=0,columnspan=3,sticky="we")
    adv_frame.grid_remove()

    def toggle_adv():
        if adv_frame.winfo_viewable(): adv_frame.grid_remove()
        else: adv_frame.grid()

    tk.Button(root,text="Options avancées ▼",command=toggle_adv).grid(row=5,column=0,columnspan=3,sticky="we")

    # Bloc Custom
    custom_frame=tk.LabelFrame(adv_frame,text="Custom")
    custom_frame.grid(row=0,column=0,sticky="we",padx=5,pady=5)
    year_var,month_var,day_var,gps_var=tk.BooleanVar(value=True),tk.BooleanVar(value=True),tk.BooleanVar(value=True),tk.BooleanVar(value=False)
    tk.Checkbutton(custom_frame,text="Année",variable=year_var).grid(row=0,column=0)
    tk.Checkbutton(custom_frame,text="Mois",variable=month_var).grid(row=0,column=1)
    tk.Checkbutton(custom_frame,text="Jour",variable=day_var).grid(row=0,column=2)
    tk.Checkbutton(custom_frame,text="GPS",variable=gps_var).grid(row=0,column=3)

    # Bloc Autres
    other_frame=tk.LabelFrame(adv_frame,text="Autres")
    other_frame.grid(row=1,column=0,sticky="we",padx=5,pady=5)
    clustering_var=tk.BooleanVar(value=False)
    clustering_cb=tk.Checkbutton(other_frame,text="Clustering",variable=clustering_var)
    clustering_cb.grid(row=0,column=0)
    tk.Label(other_frame, text="Tolérance GPS (km)").grid(row=1, column=0, sticky="w")
    threshold_var = tk.DoubleVar(value=2.0)
    tk.Entry(other_frame, textvariable=threshold_var, width=10).grid(row=1, column=1, sticky="w")

    # Activer/désactiver options selon mode
    def update_adv_state(*args):
        # Options Custom uniquement pour le mode Custom
        if sort_cb.get() == "Custom":
            for child in custom_frame.winfo_children():
                child.config(state="normal")
        else:
            for child in custom_frame.winfo_children():
                child.config(state="disabled")
        # Clustering activé si mode GPS ou mode Custom avec GPS coché
        if sort_cb.get() == "GPS":
            clustering_cb.config(state="normal")
        elif sort_cb.get() == "Custom" and gps_var.get():
            clustering_cb.config(state="normal")
        else:
            clustering_cb.config(state="disabled")
            clustering_var.set(False)

    sort_cb.bind("<<ComboboxSelected>>", update_adv_state)
    gps_var.trace_add("write", lambda *args: update_adv_state())
    update_adv_state()  # état initial

    # Bouton lancer
    def start():
        src,dst=src_entry.get(),dst_entry.get()
        if not os.path.isdir(src) or not os.path.isdir(dst):
            messagebox.showerror("Erreur","Sélectionnez des dossiers valides")
            return
        adv_options={
            "year":year_var.get(),
            "month":month_var.get(),
            "day":day_var.get(),
            "gps":gps_var.get(),
            "clustering":clustering_var.get(),
            "threshold": threshold_var.get()
        }
        sort_images(src,dst,sort_cb.get(),conflict_cb.get(),copy_cb.get(),adv_options)

    tk.Button(root,text="Démarrer",command=start).grid(row=7,column=0,columnspan=3,pady=10)

    root.mainloop()

# ----------------------------- #
# MAIN
# ----------------------------- #
if __name__=="__main__":
    build_gui()
