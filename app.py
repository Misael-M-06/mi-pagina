import os
import secrets
import hmac
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from flask_mail import Mail, Message
from datetime import datetime
from dotenv import load_dotenv
from werkzeug.security import check_password_hash

# Cargar variables de entorno
load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=True)

# Helper para leer y parsear requests.txt
REQUESTS_FILE = Path(__file__).with_name("requests.txt")

def parse_requests_file():
    if not REQUESTS_FILE.exists():
        return []

    records = []
    current = {}
    with REQUESTS_FILE.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith('-'):  # separador
                if current:
                    records.append(current)
                    current = {}
                continue

            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                current[key] = value

        if current:
            records.append(current)

    parsed = []
    for r in records:
        t = r.get('time', '')
        try:
            dt = datetime.fromisoformat(t)
        except Exception:
            dt = None
        parsed.append({
            'time': dt or t,
            'name': r.get('name', ''),
            'email': r.get('email', ''),
            'phone': r.get('phone', ''),
            'service': r.get('service', ''),
            'description': r.get('description', r.get('mensaje', '')),
        })

    parsed.sort(key=lambda x: x['time'] if isinstance(x['time'], datetime) else datetime.min, reverse=True)
    return parsed

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev_secret_change_me')

# ✅ CONFIGURACIÓN DE EMAIL
app.config['MAIL_SERVER'] = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('SMTP_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_ADDRESS')
app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('EMAIL_ADDRESS')

# Inicializar Flask-Mail
mail = Mail(app)

# Variables de configuración de email
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')
COMPANY_NAME = os.getenv('COMPANY_NAME', 'JA Molina Construction')

# Cookies de sesión para producción
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=True  # ← CAMBIAR A True para HTTPS
)

# Credenciales desde .env
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH')
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# ✅ FUNCIONES DE EMAIL - MOVIDAS AQUÍ ANTES DE SER USADAS
def send_client_confirmation_email(client_data):
    """Envía email de confirmación al cliente"""
    try:
        msg = Message(
            subject=f'Thank you for contacting {COMPANY_NAME}!',
            recipients=[client_data['email']],
            html=f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #1e4ca0, #2d5fb8); color: white; padding: 30px; text-align: center; border-radius: 10px;">
                    <h1 style="margin: 0; font-size: 2rem;">Thank You, {client_data['name']}!</h1>
                    <p style="margin: 10px 0 0; font-size: 1.1rem;">We received your request for {client_data['service']}</p>
                </div>
                
                <div style="padding: 30px 20px; background: #f8f9fa; border-radius: 10px; margin: 20px 0;">
                    <h2 style="color: #2c3e50; margin-top: 0;">What happens next?</h2>
                    <ul style="color: #555; line-height: 1.6;">
                        <li><strong>Within 24 hours:</strong> We'll review your request and contact you</li>
                        <li><strong>Free estimate:</strong> We'll schedule a convenient time to visit your property</li>
                        <li><strong>Professional service:</strong> Quality work with 1-year warranty</li>
                    </ul>
                </div>
                
                <div style="background: white; padding: 20px; border-radius: 10px; border-left: 4px solid #e53935;">
                    <h3 style="color: #2c3e50; margin-top: 0;">Your Request Details:</h3>
                    <p><strong>Service:</strong> {client_data['service']}</p>
                    <p><strong>Phone:</strong> {client_data['phone']}</p>
                    <p><strong>Description:</strong> {client_data['description']}</p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <p style="color: #666;">Questions? Call us directly:</p>
                    <a href="tel:+14439436081" style="background: #e53935; color: white; padding: 12px 25px; text-decoration: none; border-radius: 25px; font-weight: bold;">📞 (443) 943-6081</a>
                </div>
                
                <div style="text-align: center; padding: 20px; color: #666; font-size: 0.9rem;">
                    <p>{COMPANY_NAME} - Professional Construction Services in Maryland</p>
                    <p>Follow us: <a href="https://www.facebook.com/jamolinaconstruction" style="color: #1e4ca0;">Facebook</a></p>
                </div>
            </body>
            </html>
            """
        )
        mail.send(msg)
        print(f"✅ Confirmation email sent to {client_data['email']}")
        return True
    except Exception as e:
        print(f"❌ Error sending client email: {e}")
        return False

def send_admin_notification_email(client_data):
    """Envía notificación al administrador"""
    try:
        msg = Message(
            subject=f'🔔 New Request: {client_data["name"]} - {client_data["service"]}',
            recipients=[ADMIN_EMAIL],
            html=f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #e53935, #c62828); color: white; padding: 20px; text-align: center; border-radius: 10px;">
                    <h1 style="margin: 0;">🔔 New Lead Alert!</h1>
                    <p style="margin: 10px 0 0; font-size: 1.1rem;">A potential client just submitted a request</p>
                </div>
                
                <div style="background: white; padding: 20px; border-radius: 10px; margin: 20px 0; border: 2px solid #e53935;">
                    <h2 style="color: #2c3e50; margin-top: 0;">Client Information</h2>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Name:</td><td style="padding: 8px; border-bottom: 1px solid #eee;">{client_data['name']}</td></tr>
                        <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Email:</td><td style="padding: 8px; border-bottom: 1px solid #eee;"><a href="mailto:{client_data['email']}">{client_data['email']}</a></td></tr>
                        <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Phone:</td><td style="padding: 8px; border-bottom: 1px solid #eee;"><a href="tel:{client_data['phone']}">{client_data['phone']}</a></td></tr>
                        <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Service:</td><td style="padding: 8px; border-bottom: 1px solid #eee;">{client_data['service']}</td></tr>
                        <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Timeline:</td><td style="padding: 8px; border-bottom: 1px solid #eee;">{client_data.get('timeline', 'Not specified')}</td></tr>
                        <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Address:</td><td style="padding: 8px; border-bottom: 1px solid #eee;">{client_data.get('address', 'Not provided')}</td></tr>
                    </table>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3 style="color: #2c3e50; margin-top: 0;">Project Description:</h3>
                    <p style="background: white; padding: 15px; border-radius: 5px; border-left: 4px solid #e53935;">{client_data['description']}</p>
                </div>
                
                <div style="text-align: center; margin: 20px 0;">
                    <p style="color: #666; margin-bottom: 15px;">Quick Actions:</p>
                    <a href="mailto:{client_data['email']}" style="background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 0 10px;">📧 Email Client</a>
                    <a href="tel:{client_data['phone']}" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 0 10px;">📞 Call Client</a>
                </div>
                
                <div style="text-align: center; padding: 15px; color: #666; font-size: 0.9rem; border-top: 1px solid #eee;">
                    <p>Request submitted at: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                </div>
            </body>
            </html>
            """
        )
        mail.send(msg)
        print(f"✅ Admin notification sent to {ADMIN_EMAIL}")
        return True
    except Exception as e:
        print(f"❌ Error sending admin email: {e}")
        return False

# Middleware CSRF
@app.before_request
def ensure_csrf():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    g.csrf_token = session['csrf_token']

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        token = request.form.get('csrf_token')
        if not token or token != session.get('csrf_token'):
            flash('Invalid CSRF token.', 'error')
            return render_template('login.html', last_user=request.form.get('username', ''))

        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''

        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('login.html', last_user=username)

        ok = (
            username == ADMIN_USERNAME and (
                (ADMIN_PASSWORD_HASH and check_password_hash(ADMIN_PASSWORD_HASH, password))
                or
                (ADMIN_PASSWORD and hmac.compare_digest(password, ADMIN_PASSWORD))
            )
        )
        
        if ok:
            session['logged_in'] = True
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
            return render_template('login.html', last_user=username)

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        flash('Please log in to access the dashboard', 'error')
        return redirect(url_for('login'))

    requests_list = parse_requests_file()
    return render_template(
        'dashboard.html',
        username=session.get('username'),
        now=datetime.now(),
        requests_list=requests_list
    )

@app.route('/admin_m2025_panel', methods=['GET'])
def admin_panel():
    if not session.get('logged_in'):
        flash('Please log in to access the admin panel', 'error')
        return redirect(url_for('login'))
    
    requests_list = parse_requests_file()
    return render_template(
        'dashboard.html', 
        username=session.get('username'), 
        now=datetime.now(),
        requests_list=requests_list
    )

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('login'))

@app.route('/form', methods=['GET', 'POST'])
def form_view():
    if request.method == 'GET':
        prefill_data = {
            'name': request.args.get('name', ''),
            'email': request.args.get('email', ''),
            'phone': request.args.get('phone', ''),
            'service': request.args.get('service', ''),
            'description': request.args.get('description', ''),
            'timeline': request.args.get('timeline', 'asap'),
            'contact_method': request.args.get('contact_method', 'phone')
        }
        
        return render_template('formulario.html', prefill=prefill_data)
    
    if request.method == 'POST':
        token = request.form.get('csrf_token')
        if not token or token != session.get('csrf_token'):
            flash('Invalid security token. Please try again.', 'error')
            return render_template('formulario.html')

        name = request.form.get('nombre')
        email = request.form.get('email') 
        phone = request.form.get('phone')
        address = request.form.get('direccion')
        service = request.form.get('trabajo')
        timeline = request.form.get('timeline')
        description = request.form.get('descripcion')
        contact_method = request.form.get('preferred_contact')

        if not all([name, email, phone, service, description]):
            flash('Please fill in all required fields.', 'error')
            return render_template('formulario.html')

        client_data = {
            'name': name,
            'email': email,
            'phone': phone,
            'address': address or 'Not provided',
            'service': service.replace('-', ' ').title(),
            'timeline': timeline,
            'description': description,
            'contact_method': contact_method
        }

        try:
            with open('requests.txt', 'a', encoding='utf-8') as f:
                f.write('-' * 50 + '\n')
                f.write(f'Time: {datetime.now().isoformat()}\n')
                f.write(f'Name: {name}\n')
                f.write(f'Email: {email}\n')
                f.write(f'Phone: {phone}\n')
                f.write(f'Address: {address}\n')
                f.write(f'Service: {service}\n')
                f.write(f'Timeline: {timeline}\n')
                f.write(f'Contact Method: {contact_method}\n')
                f.write(f'Description: {description}\n')
                f.write('\n')
            print("✅ Solicitud guardada exitosamente en requests.txt")
            
            print("📧 Sending confirmation emails...")
            
            client_email_sent = send_client_confirmation_email(client_data)
            admin_email_sent = send_admin_notification_email(client_data)
            
            if client_email_sent and admin_email_sent:
                print("✅ All emails sent successfully!")
                flash("Thank you! Your request has been sent successfully. Check your email for confirmation!", 'success')
            elif client_email_sent:
                print("⚠️ Client email sent, admin email failed")
                flash("Thank you! Your request has been sent successfully. Check your email for confirmation!", 'success')
            else:
                print("⚠️ Emails failed, but request was saved")
                flash("Thank you! Your request has been sent successfully. We'll contact you soon!", 'success')
                
        except Exception as e:
            print('❌ Error guardando solicitud:', e)
            flash('There was an error processing your request. Please try again.', 'error')
            return render_template('formulario.html')

        return redirect(url_for('home'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)


