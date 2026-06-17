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
    
    is_admin = db.Column(db.Boolean, default=False) # <- ESTE É O ADMIN MASTER
    is_professor = db.Column(db.Boolean, default=False)
    
    # NOVOS CAMPOS DO PERFIL DO PROFESSOR
    cpf = db.Column(db.String(14), nullable=True)
    data_nascimento = db.Column(db.String(10), nullable=True)
    sexo = db.Column(db.String(20), nullable=True)
    cep = db.Column(db.String(10), nullable=True)
    foto_perfil = db.Column(db.String(255), default='default.png')
    
    # Campos de escala/função
    funcao_papeis = db.Column(db.String(20), default='professor') 
    disponibilidade_dias = db.Column(db.String(200), nullable=True)
    classes_preferidas = db.Column(db.String(100), nullable=True)
    
    # NOVA TRAVA DE SEGURANÇA:
    pode_editar_escala = db.Column(db.Boolean, default=False) 
    
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
    foto_url = db.Column(db.String(200), nullable=True, default='default.png')

class Crianca(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    data_nascimento = db.Column(db.String(20), nullable=False)
    sexo = db.Column(db.String(20), nullable=False)
    alergias_condicoes = db.Column(db.String(200), nullable=True)
    foto_url = db.Column(db.String(200), nullable=True, default='default.png')
    responsavel_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    checkins = db.relationship('Checkin', backref='crianca', lazy=True)

    @property
    def esta_presente(self):
        checkin_ativo = Checkin.query.filter_by(crianca_id=self.id, data_hora_saida=None).first()
        return checkin_ativo is not None

class Turma(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_classe = db.Column(db.String(100), nullable=False) # Ex: "3-4", "5-6" ou "7"
    dia_aula = db.Column(db.String(50), nullable=True)      # Ex: "Domingo - 21/06" ou "Próximo Domingo"
    numeracao_escala = db.Column(db.String(20), nullable=True) # Ex: "Escala #04" ou "Semana 1"
    
    # Vínculos da Escala Automática
    professor_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    auxiliar_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    
    responsabilidade = db.Column(db.String(50), default='Professor Titular')
    disponibilidade = db.Column(db.String(50))
    turno = db.Column(db.String(50))
    status = db.Column(db.String(20), default='fechada')
    
    # Relacionamentos explícitos para buscar os nomes na segunda imagem
    professor_rel = db.relationship('Usuario', foreign_keys=[professor_id])
    auxiliar_rel = db.relationship('Usuario', foreign_keys=[auxiliar_id])
    checkins = db.relationship('Checkin', backref='turma', lazy=True)
    checkins = db.relationship('Checkin', backref='turma', lazy=True)

class Checkin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crianca_id = db.Column(db.Integer, db.ForeignKey('crianca.id'), nullable=False)
    turma_id = db.Column(db.Integer, db.ForeignKey('turma.id'), nullable=True) # Vínculo com a sala
    data_hora_entrada = db.Column(db.DateTime, default=datetime.utcnow)
    data_hora_saida = db.Column(db.DateTime, nullable=True)

class Notificacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False) # ID do Pai/Mãe que vai receber
    mensagem = db.Column(db.String(255), nullable=False)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)
    lida = db.Column(db.Boolean, default=False)

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
        
        # 1. CAPTURA A OPÇÃO MARCADA NO HTML (responsavel ou admin)
        perfil = request.form.get('perfil')

        user_existente = Usuario.query.filter_by(email=email).first()
        if user_existente:
            flash('Este e-mail já está cadastrado.', 'danger')
            return redirect(url_for('cadastro'))

        senha_criptografada = generate_password_hash(senha)
        
        # 2. SE FOR ADMIN/PROFESSOR, MARCAMOS COMO TRUE
        is_prof = True if perfil == 'admin' else False
        
        novo_usuario = Usuario(
            nome='Novo Usuário', 
            email=email,
            senha_hash=senha_criptografada,
            is_admin=False,
            is_professor=is_prof # Salva no banco de acordo com a escolha
        )
        db.session.add(novo_usuario)
        db.session.commit()

        login_user(novo_usuario)
        
        # 3. REDIRECIONA PARA A TELA CORRETA
        if is_prof:
            # Se escolheu Professor/DI, vai para o perfil do professor
            return redirect(url_for('cadastro_professor_perfil'))
        else:
            # Se escolheu Responsável, vai para o cadastro do pai/mãe
            return redirect(url_for('finalizar_cadastro'))

    return render_template('cadastro.html')

@app.route('/finalizar_cadastro', methods=['GET', 'POST'])
@login_required
def finalizar_cadastro():
    if request.method == 'POST':
        foto_nome = 'default.png'
        if 'foto' in request.files:
            foto = request.files['foto']
            if foto.filename != '':
                foto_nome = secure_filename(foto.filename)
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], foto_nome))

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
    if current_user.is_professor:
        return redirect(url_for('dashboard_professor'))

    responsavel = Responsavel.query.filter_by(usuario_id=current_user.id).first()
    criancas = Crianca.query.filter_by(usuario_id=current_user.id).all()
    
    # Busca alertas urgentes enviados pelos professores para este pai/mãe
    alertas = Notificacao.query.filter_by(usuario_id=current_user.id, lida=False).order_by(Notificacao.data_hora.desc()).all()
    
    return render_template('dashboard.html', responsavel=responsavel, criancas=criancas, alertas=alertas)

# Rota simples para o pai marcar o alerta como visto/lido
@app.route('/marcar_notificacao_lida/<int:notif_id>', methods=['POST'])
@login_required
def marcar_notificacao_lida(notif_id):
    notif = Notificacao.query.get_or_404(notif_id)
    if notif.usuario_id == current_user.id:
        notif.lida = True
        db.session.commit()
    return redirect(url_for('dashboard'))

# ==========================================
# FLUXO EXCLUSIVO DO PROFESSOR
# ==========================================
@app.route('/cadastro_professor_perfil', methods=['GET', 'POST'])
@login_required
def cadastro_professor_perfil():
    if request.method == 'POST':
        current_user.is_professor = True
        current_user.nome = request.form.get('nome')
        current_user.cpf = request.form.get('cpf')
        current_user.data_nascimento = request.form.get('data_nascimento')
        current_user.sexo = request.form.get('sexo')
        current_user.telefone = request.form.get('telefone')
        current_user.cep = request.form.get('cep')
        
        # Lógica para salvar a foto (se enviada)
        foto = request.files.get('foto')
        if foto and foto.filename != '':
            filename = secure_filename(foto.filename)
            foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.foto_perfil = filename
            
        db.session.commit()
        flash('Perfil de professor cadastrado com sucesso!', 'success')
        
        # Após o cadastro pessoal, redireciona para o dashboard (ou para a tela de disponibilidade)
        return redirect(url_for('dashboard_professor'))
        
    return render_template('cadastro_professor_perfil.html')
@app.route('/finalizar_cadastro_professor', methods=['GET', 'POST'])
@login_required
def finalizar_cadastro_professor():
    if not current_user.pode_editar_escala:
        flash('A definição de escala está fechada no momento. Fale com a diretoria.', 'danger')
        return redirect(url_for('perfil_professor'))
    if request.method == 'POST':
        current_user.is_professor = True
        current_user.nome = request.form.get('nome')
        current_user.telefone = request.form.get('telefone')
        
        # Coleta a função: 'professor', 'auxiliar' ou 'ambos'
        current_user.funcao_papeis = request.form.get('funcao_papeis')
        
        # Coleta os dias selecionados
        dias = request.form.getlist('dias_disponiveis')
        current_user.disponibilidade_dias = ", ".join(dias)
        
        # Coleta as classes preferidas (3-4, 5-6, 7)
        classes = request.form.getlist('classes_interesse')
        current_user.classes_preferidas = ", ".join(classes)
        
        db.session.commit()
        
        flash('Disponibilidade salva! O sistema gerará a escala ideal com base nos seus dados.', 'success')
        return redirect(url_for('dashboard_professor'))
        
    # Lista de classes editável centralizada para renderizar no HTML template
    classes_disponiveis = ["3-4", "5-6", "7"]
    return render_template('cadastro_professor.html', classes_disponiveis=classes_disponiveis)


@app.route('/dashboard_professor')
@login_required
def dashboard_professor():
    if not current_user.is_professor and not current_user.is_admin:
        flash('Acesso restrito.', 'danger')
        return redirect(url_for('dashboard'))
        
    # Busca todas as turmas onde o usuário atual foi alocado na escala automática (seja como professor ou auxiliar)
    turmas = Turma.query.filter(
        (Turma.professor_id == current_user.id) | (Turma.auxiliar_id == current_user.id)
    ).all()
    
    return render_template('dashboard_professor.html', turmas=turmas)

@app.route('/adicionar_classe', methods=['GET', 'POST'])
@login_required
def adicionar_classe():
    if not current_user.is_professor and not current_user.is_admin:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nova_turma = Turma(
            professor_id=current_user.id,
            nome_classe=request.form.get('classe'),
            responsabilidade=request.form.get('responsabilidade'),
            disponibilidade=request.form.get('disponibilidade'),
            turno=request.form.get('turno'),
            status='fechada'
        )
        db.session.add(nova_turma)
        db.session.commit()
        return redirect(url_for('dashboard_professor'))
        
    return render_template('adicionar_classe.html')

@app.route('/gerenciar_turma/<int:turma_id>/<string:acao>')
@login_required
def gerenciar_turma(turma_id, acao):
    turma = Turma.query.get_or_404(turma_id)
    if turma.professor_id != current_user.id and not current_user.is_admin:
        return jsonify({'erro': 'Acesso negado'}), 403

    if acao == 'iniciar_checkin':
        turma.status = 'checkin'
        db.session.commit()
        # MUDANÇA AQUI: Redireciona direto para a tela do QR Code!
        return redirect(url_for('tela_qr', turma_id=turma.id))
        
    elif acao == 'iniciar_aula':
        turma.status = 'acontecendo'
        db.session.commit()
        # MUDANÇA AQUI: Volta pro dashboard depois de "Finalizar Check-in"
        return redirect(url_for('dashboard_professor'))
        
    elif acao == 'iniciar_checkout':
        turma.status = 'checkout'
    elif acao == 'finalizar':
        turma.status = 'fechada'
        # Limpa automaticamente as presenças da sala ao fechar
        checkins_ativos = Checkin.query.filter_by(turma_id=turma.id, data_hora_saida=None).all()
        for c in checkins_ativos:
            c.data_hora_saida = datetime.utcnow()

    db.session.commit()
    return redirect(url_for('dashboard_professor'))

@app.route('/tela_qr/<int:turma_id>')
@login_required
def tela_qr(turma_id):
    turma = Turma.query.get_or_404(turma_id)
    qtd_presentes = Checkin.query.filter_by(turma_id=turma.id, data_hora_saida=None).count()
    return render_template('tela_qr.html', turma=turma, qtd_presentes=qtd_presentes)

@app.route('/lista_presenca/<int:turma_id>')
@login_required
def lista_presenca(turma_id):
    turma = Turma.query.get_or_404(turma_id)
    # Pegamos os checkins ativos e garantimos que carregue os dados da criança vinculada
    checkins = Checkin.query.filter_by(turma_id=turma.id, data_hora_saida=None).all()
    return render_template('lista_presenca.html', turma=turma, checkins=checkins)


@app.route('/chamar_responsavel/<int:crianca_id>/<int:turma_id>', methods=['POST'])
@login_required
def chamar_responsavel(crianca_id, turma_id):
    if not current_user.is_professor and not current_user.is_admin:
        return jsonify({'erro': 'Acesso negado'}), 403

    crianca = Crianca.query.get_or_404(crianca_id)
    
    # Criar a mensagem de alerta para o pai
    mensagem_alerta = f"🚨 Atenção! O professor da sala necessita da sua presença para tratar de {crianca.nome}. Por favor, dirija-se à sala."
    
    # Salva a notificação interna no banco de dados para o usuário responsável
    nova_notif = Notificacao(
        usuario_id=crianca.responsavel_id,
        mensagem=mensagem_alerta
    )
    
    db.session.add(nova_notif)
    db.session.commit()
    
    flash(f'O responsável de {crianca.nome} foi notificado no painel do site com sucesso!', 'success')
    return redirect(url_for('lista_presenca', turma_id=turma_id))

@app.route('/detalhes_crianca/<int:crianca_id>')
@login_required
def detalhes_crianca(crianca_id):
    crianca = Crianca.query.get_or_404(crianca_id)
    responsavel = Responsavel.query.filter_by(usuario_id=crianca.usuario_id).first()
    return render_template('detalhes_crianca.html', crianca=crianca, responsavel=responsavel)

# ==========================================
# OUTRAS ROTAS COMPLEMENTARES
# ==========================================

@app.route('/notificacoes')
@login_required
def notificacoes():
    return render_template('notificacoes.html')

@app.route('/configuracoes')
@login_required
def configuracoes():
    return render_template('configuracoes.html')

@app.route('/sobre_professores')
@login_required
def sobre_professores():
    return render_template('sobre_professores.html')

@app.route('/calendario')
@login_required
def calendario():
    return render_template('calendario.html')

@app.route('/politica_privacidade')
def politica_privacidade():
    return render_template('politica_privacidade.html')

@app.route('/minha_conta', methods=['GET', 'POST'])
@login_required
def minha_conta():
    if request.method == 'POST':
        current_user.nome = request.form.get('nome')
        current_user.telefone = request.form.get('telefone')
        db.session.commit()
        return redirect(url_for('configuracoes'))
    return render_template('minha_conta.html')

@app.route('/adicionar_responsavel', methods=['GET', 'POST'])
@login_required
def adicionar_responsavel():
    if request.method == 'POST':
        foto_nome = 'default.png'
        if 'foto' in request.files:
            foto = request.files['foto']
            if foto.filename != '':
                foto_nome = secure_filename(foto.filename)
                foto.save(os.path.join(app.config['UPLOAD_FOLDER'], foto_nome))

        novo_responsavel = Responsavel(
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
            usuario_id=current_user.id
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

    # Captura o ID da turma lido pelo QR Code na câmera do celular
    turma_id = request.form.get('turma_id')

    checkin_ativo = Checkin.query.filter_by(crianca_id=crianca.id, data_hora_saida=None).first()

    if checkin_ativo:
        # Se já estava presente, faz o CHECK-OUT
        checkin_ativo.data_hora_saida = datetime.utcnow()
        flash(f'Check-out de {crianca.nome} realizado!', 'success')
    else:
        # Se não estava, faz o CHECK-IN na turma lida pelo QR Code
        novo_checkin = Checkin(crianca_id=crianca.id, turma_id=turma_id)
        db.session.add(novo_checkin)
        flash(f'Check-in de {crianca.nome} realizado com sucesso!', 'success')

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

# ==========================================
# PAINEL DO ADMIN MASTER
# ==========================================
# ==========================================
# PAINEL DO ADMIN MASTER
# ==========================================
@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    # Proteção de acesso: Só o admin master entra
    if not current_user.is_admin:
        flash('Acesso negado. Área restrita à diretoria.', 'danger')
        return redirect(url_for('dashboard'))

    # Pega todos os dados do banco para o Admin ter visão geral
    professores = Usuario.query.filter_by(is_professor=True).all()
    criancas = Crianca.query.all()
    turmas = Turma.query.all()
    responsaveis = Responsavel.query.all()
    
    return render_template('admin_dashboard.html', professores=professores, criancas=criancas, turmas=turmas, responsaveis=responsaveis)

@app.route('/admin/toggle_escala/<int:prof_id>')
@login_required
def toggle_escala(prof_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
        
    prof = Usuario.query.get_or_404(prof_id)
    # Ativa/Desativa o acesso do professor para preencher a escala
    prof.pode_editar_escala = not prof.pode_editar_escala 
    db.session.commit()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/liberar_escala/<int:prof_id>')
@login_required
def liberar_escala(prof_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
        
    prof = Usuario.query.get_or_404(prof_id)
    # Inverte o status (Se estava bloqueado, libera. Se estava liberado, bloqueia)
    prof.pode_editar_escala = not prof.pode_editar_escala 
    db.session.commit()
    
    status = "liberada" if prof.pode_editar_escala else "bloqueada"
    flash(f'Escala de {prof.nome} foi {status}!', 'success')
    return redirect(url_for('admin_dashboard'))

# ==========================================
# NOVA TELA DE PERFIL/CONFIGURAÇÕES (BASEADA NA IMAGEM)
# ==========================================
@app.route('/perfil_professor')
@login_required
def perfil_professor():
    if not current_user.is_professor:
        return redirect(url_for('dashboard'))
    return render_template('perfil_professor.html')

# ==========================================
# GERAÇÃO DE DADOS DE TESTE
# ==========================================
def criar_usuario_teste():
    # 1. Usuário Responsável de Teste
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
    
    # 2. Usuário Professor de Teste
    prof = Usuario.query.filter_by(email='professor@ipjardim.com').first()
    if not prof:
        senha_prof_criptografada = generate_password_hash('123456')
        novo_prof = Usuario(
            nome='Prof. Carlos Silva',
            email='professor@ipjardim.com',
            telefone='(83) 98888-7777',
            senha_hash=senha_prof_criptografada,
            is_professor=True
        )
        db.session.add(novo_prof)
        
    db.session.commit()
    print("Contas de teste prontas!")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        criar_usuario_teste()
    app.run(host='0.0.0.0', port=5000)