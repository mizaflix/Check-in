import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ==========================================
# CONFIGURAÇÕES INICIAIS
# ==========================================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave_secreta_checkkids_ipjardim'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///checkkids.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."

# ==========================================
# MODELOS DO BANCO DE DADOS
# ==========================================
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    telefone = db.Column(db.String(20), nullable=True)
    senha_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_professor = db.Column(db.Boolean, default=False)
    criancas = db.relationship('Crianca', backref='responsavel', lazy=True)

class Responsavel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(14), nullable=False)
    data_nascimento = db.Column(db.String(10), nullable=False)
    sexo = db.Column(db.String(20), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    vinculo = db.Column(db.String(50), nullable=False)
    endereco = db.Column(db.String(200), nullable=True)
    foto_url = db.Column(db.String(200), nullable=True, default='default.png') # <--- ADICIONE ESTA LINHA

class Crianca(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    data_nascimento = db.Column(db.String(20), nullable=False)
    sexo = db.Column(db.String(20), nullable=False)
    alergias_condicoes = db.Column(db.String(200), nullable=True)
    foto_url = db.Column(db.String(200), nullable=True, default='default.png')
    responsavel_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

    @property
    def esta_presente(self):
        checkin_ativo = Checkin.query.filter_by(crianca_id=self.id, data_hora_saida=None).first()
        return checkin_ativo is not None

class Checkin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crianca_id = db.Column(db.Integer, db.ForeignKey('crianca.id'), nullable=False)
    data_hora_entrada = db.Column(db.DateTime, default=datetime.utcnow)
    data_hora_saida = db.Column(db.DateTime, nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# ==========================================
# ROTAS DO SISTEMA
# ==========================================

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        user = Usuario.query.filter_by(email=email).first()

        if user and check_password_hash(user.senha_hash, senha):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('E-mail ou senha inválidos.', 'danger')

    return render_template('login.html')


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')

        user_existente = Usuario.query.filter_by(email=email).first()
        if user_existente:
            flash('Este e-mail já está cadastrado.', 'danger')
            return redirect(url_for('cadastro'))

        senha_criptografada = generate_password_hash(senha)
        
        novo_usuario = Usuario(
            nome='Novo Usuário', 
            email=email,
            senha_hash=senha_criptografada,
            is_admin=False,
            is_professor=False
        )
        db.session.add(novo_usuario)
        db.session.commit()

        login_user(novo_usuario)
        return redirect(url_for('finalizar_cadastro')) # Redireciona para completar os dados

    return render_template('cadastro.html')

# --- FINALIZAR CADASTRO ---
# --- FINALIZAR CADASTRO (RESPONSÁVEL PRINCIPAL) ---
@app.route('/finalizar_cadastro', methods=['GET', 'POST'])
@login_required
def finalizar_cadastro():
    if request.method == 'POST':
        # 1. Lógica para salvar a foto
        foto_nome = 'default.png'
        if 'foto' in request.files:
            foto = request.files['foto']
            if foto.filename != '':
                foto_nome = secure_filename(foto.filename)
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], foto_nome))

        # 2. Salva os dados como um Responsável atrelado ao usuário que acabou de criar a conta
        responsavel_principal = Responsavel(
            usuario_id=current_user.id,
            nome=request.form.get('nome'),
            cpf=request.form.get('cpf'),
            data_nascimento=request.form.get('data_nascimento'),
            sexo=request.form.get('sexo'),
            telefone=request.form.get('telefone'),
            vinculo=request.form.get('vinculo'),
            endereco=request.form.get('endereco'),
            foto_url=foto_nome
        )
        
        db.session.add(responsavel_principal)
        db.session.commit()
        
        # Leva para o dashboard após concluir
        return redirect(url_for('dashboard'))

    return render_template('finalizar_cadastro.html')
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Busca o responsável principal (o primeiro cadastrado para este usuário)
    responsavel = Responsavel.query.filter_by(usuario_id=current_user.id).first()
    
    # Busca as crianças vinculadas a este usuário
    criancas = Crianca.query.filter_by(usuario_id=current_user.id).all()
    
    # Passamos o 'responsavel' para o HTML
    return render_template('dashboard.html', responsavel=responsavel, criancas=criancas)

# --- PÁGINA DE CONFIGURAÇÕES ---
@app.route('/configuracoes')
@login_required
def configuracoes():
    return render_template('configuracoes.html')

# --- SOBRE OS PROFESSORES ---
@app.route('/sobre_professores')
@login_required
def sobre_professores():
    return render_template('sobre_professores.html')

# --- CALENDÁRIO DO DI ---
@app.route('/calendario')
@login_required
def calendario():
    return render_template('calendario.html')

# --- POLÍTICA DE PRIVACIDADE ---
@app.route('/politica_privacidade')
def politica_privacidade():
    return render_template('politica_privacidade.html')

# --- TELA MINHA CONTA ---
@app.route('/minha_conta', methods=['GET', 'POST'])
@login_required
def minha_conta():
    if request.method == 'POST':
        current_user.nome = request.form.get('nome')
        current_user.telefone = request.form.get('telefone')
        db.session.commit()
        return redirect(url_for('configuracoes'))
    return render_template('minha_conta.html')

# --- ADICIONAR RESPONSÁVEL SECUNDÁRIO ---
@app.route('/adicionar_responsavel', methods=['GET', 'POST'])
@login_required
def adicionar_responsavel():
    if request.method == 'POST':
        # 1. Pega a foto se ela foi enviada
        foto_nome = 'default.png'
        if 'foto' in request.files:
            foto = request.files['foto']
            if foto.filename != '':
                foto_nome = secure_filename(foto.filename)
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], foto_nome))

        # 2. Cria o novo responsável no banco
        novo_responsavel = Responsavel(
            usuario_id=current_user.id,
            nome=request.form.get('nome'),
            cpf=request.form.get('cpf'),
            data_nascimento=request.form.get('data_nascimento'),
            sexo=request.form.get('sexo'),
            telefone=request.form.get('telefone'),
            vinculo=request.form.get('vinculo'),
            endereco=request.form.get('endereco'),
            foto_url=foto_nome # <--- SALVA O NOME DA FOTO
        )
        db.session.add(novo_responsavel)
        db.session.commit()
        return redirect(url_for('dashboard'))
        
    return render_template('adicionar_responsavel.html')

@app.route('/cadastrar_crianca', methods=['GET', 'POST'])
@login_required
def cadastrar_crianca():
    if request.method == 'POST':
        nome = request.form.get('nome')
        data_nascimento = request.form.get('data_nascimento')
        sexo = request.form.get('sexo')
        alergias = request.form.get('alergias_condicoes')

        foto_nome = 'default.png'
        if 'foto' in request.files:
            foto = request.files['foto']
            if foto.filename != '':
                foto_nome = secure_filename(foto.filename)
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], foto_nome))

        nova_crianca = Crianca(
            nome=nome,
            data_nascimento=data_nascimento,
            sexo=sexo,
            alergias_condicoes=alergias if alergias else "Nenhuma",
            foto_url=foto_nome,
            responsavel_id=current_user.id,
            usuario_id=current_user.id  # <--- ESTA É A LINHA QUE FALTAVA!
        )

        db.session.add(nova_crianca)
        db.session.commit()
        
        flash('Criança cadastrada com sucesso!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('cadastro_crianca.html')

@app.route('/toggle_checkin/<int:crianca_id>', methods=['POST'])
@login_required
def toggle_checkin(crianca_id):
    crianca = Crianca.query.get_or_404(crianca_id)
    
    if crianca.responsavel_id != current_user.id and not current_user.is_admin:
        return jsonify({'erro': 'Acesso negado'}), 403

    checkin_ativo = Checkin.query.filter_by(crianca_id=crianca.id, data_hora_saida=None).first()

    if checkin_ativo:
        checkin_ativo.data_hora_saida = datetime.utcnow()
    else:
        novo_checkin = Checkin(crianca_id=crianca.id)
        db.session.add(novo_checkin)

    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/realizar_checkin')
@login_required
def realizar_checkin():
    todas_criancas = Crianca.query.all()
    return render_template('checkin.html', criancas=todas_criancas)

@app.route('/escanear_qr/<int:crianca_id>')
@login_required
def escanear_qr(crianca_id):
    crianca = Crianca.query.get_or_404(crianca_id)
    return render_template('escanear_qr.html', crianca=crianca)

def criar_usuario_teste():
    user = Usuario.query.filter_by(email='teste@ipjardim.com').first()
    if not user:
        senha_criptografada = generate_password_hash('123456')
        novo_usuario = Usuario(
            nome='João Responsável', 
            email='teste@ipjardim.com', 
            telefone='(83) 99999-8888',
            senha_hash=senha_criptografada
        )
        db.session.add(novo_usuario)
        db.session.commit()
        print("Usuário de teste criado! Email: teste@ipjardim.com | Senha: 123456")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        criar_usuario_teste()
    app.run(debug=True)