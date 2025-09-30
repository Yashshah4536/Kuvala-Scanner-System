from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from datetime import datetime
import os
import qrcode
import io
import base64
from sqlalchemy import create_engine, Column, Integer, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from dotenv import load_dotenv
import pandas as pd

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Database setup (PostgreSQL via SQLAlchemy)
DATABASE_URL = os.getenv("DATABASE_URL")

Base = declarative_base()

class Scan(Base):
    __tablename__ = 'scans'
    id = Column(Integer, primary_key=True, autoincrement=True)
    qr_data = Column(Text, nullable=False)
    scan_time = Column(DateTime, default=datetime.utcnow)
    additional_info = Column(Text)

engine = None
SessionLocal = None

def init_db():
    """Initialize the database engine and create tables"""
    global engine, SessionLocal
    if not DATABASE_URL:
        raise RuntimeError(
            'DATABASE_URL environment variable is required'
        )
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    SessionLocal = scoped_session(sessionmaker(bind=engine, autocommit=False, autoflush=False))
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully")

@app.teardown_appcontext
def remove_session(exception=None):
    if SessionLocal is not None:
        SessionLocal.remove()

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/scan')
def scan():
    """QR scanning page"""
    return render_template('scan.html')

@app.route('/generate')
def generate():
    """QR generation page"""
    return render_template('generate.html')

@app.route('/records')
def records():
    """Records page"""
    return render_template('records.html')

@app.route('/api/generate-qr', methods=['POST'])
def generate_qr():
    """API endpoint to generate QR code"""
    try:
        data = request.get_json()
        user_id = data.get('id')
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        
        if not all([user_id, name, email, phone]):
            return jsonify({'success': False, 'error': 'All fields are required'}), 400
        
        # Create formatted data string
        qr_data = f"ID: {user_id}\nName: {name}\nEmail: {email}\nPhone: {phone}"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'qr_image': f'data:image/png;base64,{img_base64}',
            'qr_data': qr_data
        })
    except Exception as e:
        print(f"Error in generate_qr: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/save-scan', methods=['POST'])
def save_scan():
    """API endpoint to save QR scan data"""
    session = None
    try:
        data = request.get_json()
        qr_data = data.get('qr_data')
        additional_info = data.get('additional_info', '')
        
        print(f"Received data: {data}")
        
        if not qr_data:
            return jsonify({'success': False, 'error': 'No QR data provided'}), 400
        
        session = SessionLocal()
        
        # Create new scan with explicit field values
        new_scan = Scan(
            qr_data=str(qr_data),
            additional_info=str(additional_info) if additional_info else None,
            scan_time=datetime.utcnow()
        )
        
        session.add(new_scan)
        session.commit()
        session.refresh(new_scan)
        
        scan_id = new_scan.id
        print(f"Scan saved successfully with ID: {scan_id}")
        
        return jsonify({
            'success': True,
            'message': 'Scan saved successfully',
            'scan_id': scan_id
        })
    except Exception as e:
        print(f"Error saving scan: {str(e)}")
        if session:
            session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if session:
            session.close()

@app.route('/api/get-scans', methods=['GET'])
def get_scans():
    """API endpoint to retrieve all scans"""
    session = None
    try:
        session = SessionLocal()
        scans = session.query(Scan).order_by(Scan.scan_time.desc()).all()
        
        scans_list = []
        for scan in scans:
            scans_list.append({
                'id': scan.id,
                'qr_data': scan.qr_data,
                'scan_time': scan.scan_time.isoformat() if scan.scan_time else None,
                'additional_info': scan.additional_info
            })
        
        return jsonify({'success': True, 'scans': scans_list})
    except Exception as e:
        print(f"Error getting scans: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if session:
            session.close()

@app.route('/api/export-excel', methods=['GET'])
def export_excel():
    """API endpoint to export scans to Excel file"""
    session = None
    try:
        session = SessionLocal()
        scans = session.query(Scan).order_by(Scan.scan_time.desc()).all()
        
        if not scans:
            return jsonify({'success': False, 'error': 'No data to export'}), 404
        
        # Prepare data for Excel
        data = []
        for scan in scans:
            # Parse QR data to extract individual fields
            qr_lines = scan.qr_data.split('\n') if scan.qr_data else []
            parsed_data = {
                'ID': scan.id,
                'User ID': '',
                'Name': '',
                'Email': '',
                'Phone': '',
                'Scan Time': scan.scan_time.strftime('%Y-%m-%d %H:%M:%S') if scan.scan_time else '',
                'Additional Info': scan.additional_info or ''
            }
            
            # Parse the QR data fields
            for line in qr_lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    if key == 'ID':
                        parsed_data['User ID'] = value
                    elif key == 'Name':
                        parsed_data['Name'] = value
                    elif key == 'Email':
                        parsed_data['Email'] = value
                    elif key == 'Phone':
                        parsed_data['Phone'] = value
            
            data.append(parsed_data)
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='QR Scans', index=False)
        output.seek(0)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'qr_scans_{timestamp}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"Error exporting to Excel: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if session:
            session.close()

@app.route('/api/delete-scan/<int:scan_id>', methods=['DELETE'])
def delete_scan(scan_id):
    """API endpoint to delete a scan"""
    session = None
    try:
        session = SessionLocal()
        deleted = session.query(Scan).filter(Scan.id == scan_id).delete(synchronize_session=False)
        session.commit()
        
        if deleted:
            return jsonify({'success': True, 'message': 'Scan deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Scan not found'}), 404
    except Exception as e:
        print(f"Error deleting scan: {str(e)}")
        if session:
            session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if session:
            session.close()

@app.route('/api/clear-all', methods=['DELETE'])
def clear_all():
    """API endpoint to clear all scans"""
    session = None
    try:
        session = SessionLocal()
        session.query(Scan).delete(synchronize_session=False)
        session.commit()
        
        return jsonify({'success': True, 'message': 'All scans cleared'})
    except Exception as e:
        print(f"Error clearing scans: {str(e)}")
        if session:
            session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if session:
            session.close()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)