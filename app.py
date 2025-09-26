from flask import Flask, render_template, request
import pandas as pd
import os
import qrcode

app = Flask(__name__)

# Paths for Excel files
GENERATOR_SHEET = "generated_data.xlsx"
SCANNER_SHEET = "scanned_data.xlsx"

# Make sure "static" folder exists
if not os.path.exists("static"):
    os.makedirs("static")


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        user_id = request.form["user_id"]
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]

        # Save to generator Excel (aligned columns)
        new_entry = pd.DataFrame([[user_id, name, phone, email]],
                                 columns=["ID", "Name", "Number", "Email"])
        if os.path.exists(GENERATOR_SHEET):
            old = pd.read_excel(GENERATOR_SHEET)
            df = pd.concat([old, new_entry], ignore_index=True)
        else:
            df = new_entry
        df.to_excel(GENERATOR_SHEET, index=False)

        # Generate QR code with details as plain text
        qr_data = f"ID: {user_id}, Name: {name}, Phone: {phone}, Email: {email}"
        qr_img = qrcode.make(qr_data)
        qr_path = os.path.join("static", "qrcode.png")
        qr_img.save(qr_path)

        return render_template("index.html", qr_generated=True, qr_file="qrcode.png", qr_data=qr_data)

    return render_template("index.html", qr_generated=False)


@app.route("/scan")
def scan():
    return render_template("scan.html")


@app.route("/save_scan", methods=["POST"])
def save_scan():
    scanned_text = request.form["data"]

    # Parse the scanned text
    try:
        parts = scanned_text.split(", ")
        parsed = {}
        for part in parts:
            key, value = part.split(": ", 1)
            parsed[key.strip()] = value.strip()

        user_id = parsed.get("ID", "")
        name = parsed.get("Name", "")
        phone = parsed.get("Phone", "")
        email = parsed.get("Email", "")

        # Save parsed data into structured Excel (same structure as generator)
        new_entry = pd.DataFrame([[user_id, name, phone, email]],
                                 columns=["ID", "Name", "Number", "Email"])
    except Exception as e:
        # fallback: save raw text if parsing fails
        new_entry = pd.DataFrame([[scanned_text]], columns=["Scanned Data"])

    # Append to Excel
    if os.path.exists(SCANNER_SHEET):
        old = pd.read_excel(SCANNER_SHEET)
        df = pd.concat([old, new_entry], ignore_index=True)
    else:
        df = new_entry
    df.to_excel(SCANNER_SHEET, index=False)

    return "Saved"


if __name__ == "__main__":
    app.run(debug=True)


#https://script.google.com/macros/s/AKfycbxvozJfoIxPRMA9g6g9XohH8ufNBM3BqE-nlLOaHshpe8dK710Urxw73X-gcanriboE3g/exec