import sys
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory, \
    Response, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, DateTimeField, validators, PasswordField, FileField, BooleanField
from wtforms.widgets import TextInput
import phonenumbers
from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from werkzeug.utils import secure_filename
import io
from sqlalchemy import or_, and_
from xlsxwriter import Workbook
from io import BytesIO
from pywebpush import webpush, WebPushException
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import getpass
import winreg as reg
import email
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

def backup_database():
    """Функция для создания бэкапа базы данных"""
    try:
        # Создаем папку для бэкапов в той же директории, где находится скрипт
        backup_dir = Path(__file__).parent / 'backups'
        backup_dir.mkdir(exist_ok=True)

        # Формируем имя файла с текущей датой и временем
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_file = backup_dir / f'backup_{timestamp}.sql'

        # Полный путь к pg_dump (может отличаться в зависимости от установки PostgreSQL)
        pg_dump_path = r'C:\Program Files\PostgreSQL\17\bin\pg_dump.exe'

        # Проверяем существует ли pg_dump по указанному пути
        if not Path(pg_dump_path).exists():
            # Если нет, пытаемся найти в PATH
            pg_dump_path = 'pg_dump'

        # Команда для создания бэкапа PostgreSQL
        cmd = [
            pg_dump_path,
            '-U', 'postgres',
            '-h', 'localhost',
            '-d', 'postgres',
            '-f', str(backup_file)
        ]

        # Запускаем процесс бэкапа
        env = os.environ.copy()
        env['PGPASSWORD'] = '12345'

        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True  # Важно для Windows
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode('utf-8', errors='replace')
            app.logger.error(f"Ошибка при создании бэкапа: {error_msg}")
        else:
            app.logger.info(f"Создан бэкап базы данных: {backup_file}")

            # Удаляем бэкапы старше 24 часов
            current_time = datetime.now()
            for backup in backup_dir.glob('backup_*.sql'):
                backup_time = datetime.strptime(backup.stem.replace('backup_', ''), '%Y-%m-%d_%H-%M-%S')
                if (current_time - backup_time).total_seconds() > 24 * 3600:
                    try:
                        backup.unlink()
                        app.logger.info(f"Удален старый бэкап: {backup.name} (создан {backup_time})")
                    except Exception as e:
                        app.logger.error(f"Ошибка при удалении старого бэкапа {backup.name}: {str(e)}")

    except Exception as e:
        app.logger.error(f"Ошибка при создании бэкапа: {str(e)}")


def backup_scheduler():
    """Функция для периодического выполнения бэкапов"""
    while True:
        backup_database()
        # Проверяем и чистим старые бэкапы каждый час
        time.sleep(3600)

def add_to_startup():
    # Получаем путь к текущему скрипту
    script_path = os.path.abspath(__file__)
    pythonw_path = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")

    # Создаем содержимое VBS-скрипта
    vbs_script = f'''
Set WshShell = CreateObject("WScript.Shell") 
WshShell.Run "{pythonw_path} ""{script_path}""", 0
Set WshShell = Nothing
'''

    # Путь для сохранения VBS-скрипта
    startup_folder = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
    vbs_path = os.path.join(startup_folder, 'run_transport_system.vbs')

    # Записываем VBS-скрипт
    with open(vbs_path, 'w') as f:
        f.write(vbs_script)

    # Альтернативный способ через реестр
    try:
        key = reg.OpenKey(
            reg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, reg.KEY_SET_VALUE
        )
        reg.SetValueEx(key, "TransportSystem", 0, reg.REG_SZ, f'"{pythonw_path}" "{script_path}"')
        reg.CloseKey(key)
        return True
    except Exception as e:
        print(f"Ошибка при добавлении в автозагрузку: {str(e)}")
        return False


def remove_from_startup():
    try:
        # Удаляем VBS-скрипт
        startup_folder = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs',
                                      'Startup')
        vbs_path = os.path.join(startup_folder, 'run_transport_system.vbs')
        if os.path.exists(vbs_path):
            os.remove(vbs_path)

        # Удаляем запись из реестра
        key = reg.OpenKey(
            reg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, reg.KEY_SET_VALUE
        )
        reg.DeleteValue(key, "TransportSystem")
        reg.CloseKey(key)
        return True
    except Exception as e:
        print(f"Ошибка при удалении из автозагрузки: {str(e)}")
        return False


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:12345@localhost/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = '1337'

SMTP_SERVER = "khb-smtp.hg.loc"
SMTP_PORT = 25

# КЛЮЧИ ДЛЯ PUSH УВЕДОМЛЕНИЙ (ДЛЯ РАБОТЫ НУЖЕН HTTPS)
app.config[
    'VAPID_PUBLIC_KEY'] = '<cryptography.hazmat.bindings._rust.openssl.ec.ECPublicKey object at 0x000001CD890BF1B0>'
app.config[
    'VAPID_PRIVATE_KEY'] = '<cryptography.hazmat.bindings._rust.openssl.ec.ECPrivateKey object at 0x000001CD88BB99F0>'
app.config['VAPID_CLAIMS'] = {
    "sub": "mailto:УказываемИмейлЕслиПодписалсяНаУведомы@example.com"
}

db = SQLAlchemy(app)


def send_email(to_email, subject, message):
    """Функция для отправки email уведомлений"""
    try:
        # Проверяем, что email существует и валиден
        if not to_email or not isinstance(to_email, str) or '@' not in to_email:
            app.logger.error(f"Invalid email address: {to_email}")
            return False

        msg = MIMEMultipart()
        msg["From"] = "SUAT@highlangold.com"  # Это может быть любой служебный адрес
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.send_message(msg)
        return True
    except Exception as e:
        app.logger.error(f"Email sending error to {to_email}: {e}")
        return False

# БД
class Role(db.Model):
    __tablename__ = 'role'
    role_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))

class EditTimeForm(FlaskForm):
    booking_datetime = DateTimeField('Начало', format='%Y-%m-%dT%H:%M',
                                     validators=[validators.InputRequired()])
    booking_end = DateTimeField('Окончание', format='%Y-%m-%dT%H:%M',
                                validators=[validators.InputRequired()])

class Notification(db.Model):
    __tablename__ = 'notification'
    notification_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('db_authorization.auth_id'), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('DBAuthorization', backref='notifications')

    @staticmethod
    def create_notification(user_id, message):
        try:
            notification = Notification(
                user_id=user_id,
                message=message
            )
            db.session.add(notification)
            db.session.commit()

            return True
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error creating notification: {str(e)}")
            return False


class UserRole(db.Model):
    __tablename__ = 'user_role'
    user_role_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('db_authorization.auth_id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.role_id'), nullable=False)
    role = db.relationship('Role', backref='user_roles')
    user = db.relationship('DBAuthorization', backref='user_roles')


class Transport(db.Model):
    __tablename__ = 'transport'
    transport_id = db.Column(db.Integer, primary_key=True)
    tsname = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    tsnumber = db.Column(db.String(10), nullable=False)
    requires_attachment = db.Column(db.Boolean, default=False)
    is_available = db.Column(db.Boolean, default=True)


class Employee(db.Model):
    __tablename__ = 'employee'
    employee_id = db.Column(db.Integer, primary_key=True)
    firstname = db.Column(db.String(100))
    secondname = db.Column(db.String(100))
    surname = db.Column(db.String(100))
    department = db.Column(db.String(100))
    job_title = db.Column(db.String(100))
    email = db.Column(db.String(100), nullable = False)


class DBAuthorization(db.Model):
    __tablename__ = 'db_authorization'
    auth_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.employee_id'), nullable=False)
    login = db.Column(db.String(40), nullable=False, unique=True)
    password_hash = db.Column(db.String(200), nullable=False)
    employee = db.relationship('Employee', backref='auth')

    def has_role(self, role_name):
        return any(ur.role.name == role_name for ur in self.user_roles)


class Request(db.Model):
    __tablename__ = 'request'
    request_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.employee_id'), nullable=False)
    transport_id = db.Column(db.Integer, db.ForeignKey('transport.transport_id'), nullable=True)
    user_transport_id = db.Column(db.Integer, db.ForeignKey('ts_user.tsuser_id'), nullable=True)
    phone_number = db.Column(db.String(20), nullable=False)
    purpose = db.Column(db.String(600), nullable=False)
    attachment_filename = db.Column(db.String(255))
    attachment_data = db.Column(db.LargeBinary)
    attachment_mimetype = db.Column(db.String(100))
    request_datetime = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    booking_datetime = db.Column(db.DateTime, nullable=False)
    booking_end = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Interval, nullable=True)
    loc_from = db.Column(db.String(255), nullable=False)
    loc_to = db.Column(db.String(255), nullable=True)
    employee = db.relationship('Employee', backref='requests')
    transport = db.relationship('Transport', backref='requests')
    user_transport = db.relationship('TsUser', backref='requests')
    is_canceled = db.Column(db.Boolean, default=False)
    # Добавьте это поле
    use_without_kmu = db.Column(db.Boolean, default=False)


class TsUser(db.Model):
    __tablename__ = 'ts_user'
    tsuser_id = db.Column(db.Integer, primary_key=True)
    userts_name = db.Column(db.String(100), nullable=False)


class Approval(db.Model):
    __tablename__ = 'approval'
    approval_id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('request.request_id'), nullable=False)
    approval_status = db.Column(db.String(100), default='Pending')
    approver_id = db.Column(db.Integer, db.ForeignKey('db_authorization.auth_id'), nullable=True)
    approval_date = db.Column(db.DateTime, nullable=True)
    comment = db.Column(db.String(500), nullable=True)
    request = db.relationship('Request', backref='approvals')
    approver = db.relationship('DBAuthorization')

    @property
    def display_status(self):
        if self.request.is_canceled:
            return "Canceled"
        return self.approval_status


# ФОРМЫ
class PhoneNumberValidator:
    def __init__(self, message=None):
        self.message = message or 'Пожалуйста, введите корректный номер телефона в формате +7(XXX)XXX-XX-XX'

    def __call__(self, form, field):
        try:
            phone = phonenumbers.parse(field.data, None)
            if not phonenumbers.is_valid_number(phone):
                raise validators.ValidationError(self.message)
        except:
            raise validators.ValidationError(self.message)

        @property
        def display_status(self):
            if self.request.is_canceled:
                return "Canceled"
            return self.approval_status


def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


class BookingForm(FlaskForm):
    surname = StringField('Фамилия', validators=[validators.InputRequired()])
    firstname = StringField('Имя', validators=[validators.InputRequired()])
    secondname = StringField('Отчество')
    department = SelectField('Отдел', validators=[validators.InputRequired()], choices=[
        ('Отделение пробирного анализа', 'Отделение пробирного анализа'),
        ('Отдел информационных технологий', 'Отдел информационных технологий'),
        ('Отдел по режиму и сохранности', 'Отдел по режиму и сохранности'),
        ('Маркшейдерский отдел', 'Маркшейдерский отдел'),
        ('Отдел буровзрывных работ', 'Отдел буровзрывных работ'),
        ('Производственно-технический отдел', 'Производственно-технический отдел'),
        ('Химико-аналитическая лаборатория', 'Химико-аналитическая лаборатория'),
        ('Участок автоматизированных систем управления технологическим процессом',
         'Участок автоматизированных систем управления технологическим процессом'),
        ('Участок ремонта электрооборудования фабрики', 'Участок ремонта электрооборудования фабрики'),
        ('Участок сетей и подстанций', 'Участок сетей и подстанций'),
        ('Участок тепловодоснабжения и канализации', 'Участок тепловодоснабжения и канализации'),
        ('Электротехническая лаборатория', 'Электротехническая лаборатория'),
        ('Служба охраны труда и промышленной безопасности', 'Служба охраны труда и промышленной безопасности'),
        ('Медицинский пункт', 'Медицинский пункт'),
        ('Участок внутрикарьерных дорог и осушения', 'Участок внутрикарьерных дорог и осушения'),
        ('Участок диспетчеризации', 'Участок диспетчеризации'),
        ('Участок открытых горных работ', 'Участок открытых горных работ'),
        ('Отдел капитального строительства', 'Отдел капитального строительства'),
        ('Геологический отдел', 'Геологический отдел'),
        ('Отдел ресурсной геологии', 'Отдел ресурсной геологии'),
        ('Отдел обеспечения производства', 'Отдел обеспечения производства'),
        ('Склад горюче-смазочных материалов', 'Склад горюче-смазочных материалов'),
        ('Склад сильнодействующих ядовитых веществ', 'Склад сильнодействующих ядовитых веществ'),
        ('Склад товарно-материальных ценностей', 'Склад товарно-материальных ценностей'),
        ('Отдел главного инженера', 'Отдел главного инженера'),
        ('Отделение рудоподготовки', 'Отделение рудоподготовки'),
        ('Отделение товарной продукции', 'Отделение товарной продукции'),
        ('Отделение флотации, обезвоживания и реагентики', 'Отделение флотации, обезвоживания и реагентики'),
        ('Участок гидротехнических сооружений', 'Участок гидротехнических сооружений'),
        ('Автотранспортный участок', 'Автотранспортный участок'),
        ('Отдел планирования ремонтов', 'Отдел планирования ремонтов'),
        ('Ремонтно-механический участок', 'Ремонтно-механический участок'),
        ('Участок ремонта оборудования фабрики', 'Участок ремонта оборудования фабрики'),
        ('Участок ремонта самоходной техники', 'Участок ремонта самоходной техники'),
        ('Административно-хозяйственный отдел', 'Административно-хозяйственный отдел'),
        ('Отдел управления персоналом', 'Отдел управления персоналом'),
        ('Отдел бюджетирования и экономического анализа', 'Отдел бюджетирования и экономического анализа'),
        ('Администрация', 'Администрация'),
        ('Бизнес-система', 'Бизнес-система'),
        ('Отдел бухгалтерского учета и отчетности', 'Отдел бухгалтерского учета и отчетности'),
        ('Отдел охраны окружающей среды', 'Отдел охраны окружающей среды'),
        ('Отдел технического контроля', 'Отдел технического контроля'),
        ('Проектный офис', 'Проектный офис'),
        ('ПО Отдел бюджетного планирования', 'ПО Отдел бюджетного планирования'),
        ('ПО Сметный отдел', 'ПО Сметный отдел'),
        ('ПО Административно-хозяйственный отдел', 'ПО Административно-хозяйственный отдел'),
        ('ПО Отдел исполнительной документации', 'ПО Отдел исполнительной документации'),
        ('ПО Отдел промышленной безопасности и охраны труда', 'ПО Отдел промышленной безопасности и охраны труда'),
        ('ПО Отдел строительного контроля', 'ПО Отдел строительного контроля'),
        ('Проектный офис №2 Объекты перерабатывающего комплекса',
         'Проектный офис №2 Объекты перерабатывающего комплекса'),
        ('Проектный офис №3 Объекты энергетики', 'Проектный офис №3 Объекты энергетики'),
        ('ПО Производственно-технический отдел', 'ПО Производственно-технический отдел'),
        ('ПО Отдел информационных технологий', 'ПО Отдел информационных технологий'),
        ('ПО Управление информационных технологий', 'ПО Управление информационных технологий')
    ])
    job_title = StringField('Должность', validators=[validators.InputRequired()])
    transport_id = SelectField('Транспорт', coerce=int, validators=[validators.InputRequired()])
    phone_number = StringField('Телефон',
                               validators=[validators.InputRequired(), PhoneNumberValidator()],
                               widget=TextInput(),
                               render_kw={"placeholder": "+7(XXX)XXX-XX-XX"})
    purpose = TextAreaField('Цель поездки', validators=[validators.InputRequired()])
    attachment = FileField('Прикрепить файл')
    booking_datetime = DateTimeField('Начало', format='%Y-%m-%dT%H:%M',
                                     validators=[validators.InputRequired()],
                                     default=lambda: datetime.now() + timedelta(minutes=5))
    booking_end = DateTimeField('Окончание', format='%Y-%m-%dT%H:%M',
                                validators=[validators.InputRequired()])
    loc_from = StringField('Место подачи', validators=[validators.InputRequired()])
    loc_to = StringField('Место назначения', validators=[validators.Optional()])
    use_without_kmu = BooleanField('Использовать без установки', validators=[validators.Optional()])

    def __init__(self, *args, **kwargs):
        super(BookingForm, self).__init__(*args, **kwargs)

        # ПРОВЕРЯЕМ РОЛЬ ЮЗЕРА
        user_id = session.get('user_id')
        is_dispatcher = False
        if user_id:
            auth = DBAuthorization.query.get(user_id)
            is_dispatcher = auth and auth.has_role('dispatcher')

        if is_dispatcher:
            # ДИСПЕТЧЕР ВИДИТ ВЕСЬ ТРАНСПОРТ
            transports = Transport.query.filter_by(is_available=True).order_by(Transport.tsname).all()
            self.transport_id.choices = [
                (t.transport_id, f"{t.tsname} - {t.brand} {t.model} ({t.tsnumber})")
                for t in transports
            ]
        else:
            # ОГРАНИЧЕНИЕ ДУБЛИРОВАНИЯ ПО TSNAME ДЛЯ ПОЛЬЗОВАТЕЛЯ
            unique_transports = db.session.query(
                Transport.tsname,
                Transport.brand,
                Transport.model,
                Transport.tsnumber,
                Transport.transport_id,
                Transport.requires_attachment
            ).distinct(Transport.tsname).order_by(Transport.tsname).all()

            self.transport_id.choices = [
                (t.transport_id, f"{t.tsname} - {t.brand} {t.model} ({t.tsnumber})")
                for t in unique_transports
            ]

    def validate_attachment(self, field):
        transport = Transport.query.get(self.transport_id.data)
        # Проверяем, требуется ли документ (транспорт требует документ И не выбран вариант "без установки")
        if (transport and transport.requires_attachment and
                not self.use_without_kmu.data and
                not field.data):
            raise validators.ValidationError('Для данного транспорта необходимо прикрепить файл')


class LoginForm(FlaskForm):
    login = StringField('Логин', validators=[validators.InputRequired()])
    password = PasswordField('Пароль', validators=[validators.InputRequired()])


# ВЫПАДАЮЩИЙ СПИСОК ПОДРАЗДЕЛЕНИЙ ПРИ РЕГИСТРАЦИИ НОВОГО ПОЛЬЗОВАТЕЛЯ
class AddUserForm(FlaskForm):
    firstname = StringField('Имя', validators=[validators.InputRequired()])
    secondname = StringField('Отчество')
    surname = StringField('Фамилия', validators=[validators.InputRequired()])
    email = StringField('Email', validators=[validators.Optional(), validators.Email()])
    department = SelectField('Отдел', validators=[validators.InputRequired()], choices=[
        ('Отделение пробирного анализа', 'Отделение пробирного анализа'),
        ('Отдел информационных технологий', 'Отдел информационных технологий'),
        ('Отдел по режиму и сохранности', 'Отдел по режиму и сохранности'),
        ('Маркшейдерский отдел', 'Маркшейдерский отдел'),
        ('Отдел буровзрывных работ', 'Отдел буровзрывных работ'),
        ('Производственно-технический отдел', 'Производственно-технический отдел'),
        ('Химико-аналитическая лаборатория', 'Химико-аналитическая лаборатория'),
        ('Участок автоматизированных систем управления технологическим процессом',
         'Участок автоматизированных систем управления технологическим процессом'),
        ('Участок ремонта электрооборудования фабрики', 'Участок ремонта электрооборудования фабрики'),
        ('Участок сетей и подстанций', 'Участок сетей и подстанций'),
        ('Участок тепловодоснабжения и канализации', 'Участок тепловодоснабжения и канализации'),
        ('Электротехническая лаборатория', 'Электротехническая лаборатория'),
        ('Служба охраны труда и промышленной безопасности', 'Служба охраны труда и промышленной безопасности'),
        ('Медицинский пункт', 'Медицинский пункт'),
        ('Участок внутрикарьерных дорог и осушения', 'Участок внутрикарьерных дорог и осушения'),
        ('Участок диспетчеризации', 'Участок диспетчеризации'),
        ('Участок открытых горных работ', 'Участок открытых горных работ'),
        ('Отдел капитального строительства', 'Отдел капитального строительства'),
        ('Геологический отдел', 'Геологический отдел'),
        ('Отдел ресурсной геологии', 'Отдел ресурсной геологии'),
        ('Отдел обеспечения производства', 'Отдел обеспечения производства'),
        ('Склад горюче-смазочных материалов', 'Склад горюче-смазочных материалов'),
        ('Склад сильнодействующих ядовитых веществ', 'Склад сильнодействующих ядовитых веществ'),
        ('Склад товарно-материальных ценностей', 'Склад товарно-материальных ценностей'),
        ('Отдел главного инженера', 'Отдел главного инженера'),
        ('Отделение рудоподготовки', 'Отделение рудоподготовки'),
        ('Отделение товарной продукции', 'Отделение товарной продукции'),
        ('Отделение флотации, обезвоживания и реагентики', 'Отделение флотации, обезвоживания и реагентики'),
        ('Участок гидротехнических сооружений', 'Участок гидротехнических сооружений'),
        ('Автотранспортный участок', 'Автотранспортный участок'),
        ('Отдел планирования ремонтов', 'Отдел планирования ремонтов'),
        ('Ремонтно-механический участок', 'Ремонтно-механический участок'),
        ('Участок ремонта оборудования фабрики', 'Участок ремонта оборудования фабрики'),
        ('Участок ремонта самоходной техники', 'Участок ремонта самоходной техники'),
        ('Административно-хозяйственный отдел', 'Административно-хозяйственный отдел'),
        ('Отдел управления персоналом', 'Отдел управления персоналом'),
        ('Отдел бюджетирования и экономического анализа', 'Отдел бюджетирования и экономического анализа'),
        ('Администрация', 'Администрация'),
        ('Бизнес-система', 'Бизнес-система'),
        ('Отдел бухгалтерского учета и отчетности', 'Отдел бухгалтерского учета и отчетности'),
        ('Отдел охраны окружающей среды', 'Отдел охраны окружающей среды'),
        ('Отдел технического контроля', 'Отдел технического контроля'),
        ('Проектный офис', 'Проектный офис'),
        ('ПО Отдел бюджетного планирования', 'ПО Отдел бюджетного планирования'),
        ('ПО Сметный отдел', 'ПО Сметный отдел'),
        ('ПО Административно-хозяйственный отдел', 'ПО Административно-хозяйственный отдел'),
        ('ПО Отдел исполнительной документации', 'ПО Отдел исполнительной документации'),
        ('ПО Отдел промышленной безопасности и охраны труда', 'ПО Отдел промышленной безопасности и охраны труда'),
        ('ПО Отдел строительного контроля', 'ПО Отдел строительного контроля'),
        ('Проектный офис №2 Объекты перерабатывающего комплекса',
         'Проектный офис №2 Объекты перерабатывающего комплекса'),
        ('Проектный офис №3 Объекты энергетики', 'Проектный офис №3 Объекты энергетики'),
        ('ПО Производственно-технический отдел', 'ПО Производственно-технический отдел'),
        ('ПО Отдел информационных технологий', 'ПО Отдел информационных технологий'),
        ('ПО Управление информационных технологий', 'ПО Управление информационных технологий')
    ])
    job_title = StringField('Должность', validators=[validators.InputRequired()])
    login = StringField('Логин', validators=[validators.InputRequired()])
    password = PasswordField('Пароль', validators=[validators.InputRequired()])


class EditUserForm(FlaskForm):
    firstname = StringField('Имя', validators=[validators.InputRequired()])
    secondname = StringField('Отчество')
    surname = StringField('Фамилия', validators=[validators.InputRequired()])
    email = StringField('Email', validators=[validators.Optional(), validators.Email()])
    department = SelectField('Отдел', validators=[validators.InputRequired()], choices=[
        ('Отделение пробирного анализа', 'Отделение пробирного анализа'),
        ('Отдел информационных технологий', 'Отдел информационных технологий'),
        ('Отдел по режиму и сохранности', 'Отдел по режиму и сохранности'),
        ('Маркшейдерский отдел', 'Маркшейдерский отдел'),
        ('Отдел буровзрывных работ', 'Отдел буровзрывных работ'),
        ('Производственно-технический отдел', 'Производственно-технический отдел'),
        ('Химико-аналитическая лаборатория', 'Химико-аналитическая лаборатория'),
        ('Участок автоматизированных систем управления технологическим процессом',
         'Участок автоматизированных систем управления технологическим процессом'),
        ('Участок ремонта электрооборудования фабрики', 'Участок ремонта электрооборудования фабрики'),
        ('Участок сетей и подстанций', 'Участок сетей и подстанций'),
        ('Участок тепловодоснабжения и канализации', 'Участок тепловодоснабжения и канализации'),
        ('Электротехническая лаборатория', 'Электротехническая лаборатория'),
        ('Служба охраны труда и промышленной безопасности', 'Служба охраны труда и промышленной безопасности'),
        ('Медицинский пункт', 'Медицинский пункт'),
        ('Участок внутрикарьерных дорог и осушения', 'Участок внутрикарьерных дорог и осушения'),
        ('Участок диспетчеризации', 'Участок диспетчеризации'),
        ('Участок открытых горных работ', 'Участок открытых горных работ'),
        ('Отдел капитального строительства', 'Отдел капитального строительства'),
        ('Геологический отдел', 'Геологический отдел'),
        ('Отдел ресурсной геологии', 'Отдел ресурсной геологии'),
        ('Отдел обеспечения производства', 'Отдел обеспечения производства'),
        ('Склад горюче-смазочных материалов', 'Склад горюче-смазочных материалов'),
        ('Склад сильнодействующих ядовитых веществ', 'Склад сильнодействующих ядовитых веществ'),
        ('Склад товарно-материальных ценностей', 'Склад товарно-материальных ценностей'),
        ('Отдел главного инженера', 'Отдел главного инженера'),
        ('Отделение рудоподготовки', 'Отделение рудоподготовки'),
        ('Отделение товарной продукции', 'Отделение товарной продукции'),
        ('Отделение флотации, обезвоживания и реагентики', 'Отделение флотации, обезвоживания и реагентики'),
        ('Участок гидротехнических сооружений', 'Участок гидротехнических сооружений'),
        ('Автотранспортный участок', 'Автотранспортный участок'),
        ('Отдел планирования ремонтов', 'Отдел планирования ремонтов'),
        ('Ремонтно-механический участок', 'Ремонтно-механический участок'),
        ('Участок ремонта оборудования фабрики', 'Участок ремонта оборудования фабрики'),
        ('Участок ремонта самоходной техники', 'Участок ремонта самоходной техники'),
        ('Административно-хозяйственный отдел', 'Административно-хозяйственный отдел'),
        ('Отдел управления персоналом', 'Отдел управления персоналом'),
        ('Отдел бюджетирования и экономического анализа', 'Отдел бюджетирования и экономического анализа'),
        ('Администрация', 'Администрация'),
        ('Бизнес-система', 'Бизнес-система'),
        ('Отдел бухгалтерского учета и отчетности', 'Отдел бухгалтерского учета и отчетности'),
        ('Отдел охраны окружающей среды', 'Отдел охраны окружающей среды'),
        ('Отдел технического контроля', 'Отдел технического контроля'),
        ('Проектный офис', 'Проектный офис'),
        ('ПО Отдел бюджетного планирования', 'ПО Отдел бюджетного планирования'),
        ('ПО Сметный отдел', 'ПО Сметный отдел'),
        ('ПО Административно-хозяйственный отдел', 'ПО Административно-хозяйственный отдел'),
        ('ПО Отдел исполнительной документации', 'ПО Отдел исполнительной документации'),
        ('ПО Отдел промышленной безопасности и охраны труда', 'ПО Отдел промышленной безопасности и охраны труда'),
        ('ПО Отдел строительного контроля', 'ПО Отдел строительного контроля'),
        ('Проектный офис №2 Объекты перерабатывающего комплекса',
         'Проектный офис №2 Объекты перерабатывающего комплекса'),
        ('Проектный офис №3 Объекты энергетики', 'Проектный офис №3 Объекты энергетики'),
        ('ПО Производственно-технический отдел', 'ПО Производственно-технический отдел'),
        ('ПО Отдел информационных технологий', 'ПО Отдел информационных технологий'),
        ('ПО Управление информационных технологий', 'ПО Управление информационных технологий')
    ])
    job_title = StringField('Должность', validators=[validators.InputRequired()])
    login = StringField('Логин', validators=[validators.InputRequired()])


class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Текущий пароль', validators=[validators.InputRequired()])
    new_password = PasswordField('Новый пароль', validators=[
        validators.InputRequired(),
        validators.Length(min=6, message='Пароль должен быть не менее 6 символов')
    ])
    confirm_password = PasswordField('Подтвердите новый пароль', validators=[
        validators.InputRequired(),
        validators.EqualTo('new_password', message='Пароли должны совпадать')
    ])


class RequestStatusForm(FlaskForm):
    status = SelectField('Статус', choices=[
        ('Pending', 'На рассмотрении'),
        ('Approved', 'Одобрено'),
        ('Rejected', 'Отклонено')
    ], validators=[validators.InputRequired()])
    transport_id = SelectField('Назначить транспорт', coerce=int, validators=[validators.Optional()])
    comment = TextAreaField('Комментарий', validators=[validators.Optional()])

    def __init__(self, *args, **kwargs):
        super(RequestStatusForm, self).__init__(*args, **kwargs)
        # ФИЛЬТРАЦИЯ ТОЛЬКО ДОСТУПНОГО ТРАНСПОРТА (ДЛЯ ДИСПЕТЧЕРА ПРИ РАБОТЕ С ЗАЯВКОЙ)
        self.transport_id.choices = [
            (t.transport_id, f"{t.tsname} - {t.brand} {t.model} ({t.tsnumber})")
            for t in Transport.query.filter_by(is_available=True).order_by(Transport.tsname).all()
        ]
        self.transport_id.choices.insert(0, (0, 'Не изменять'))


def create_password_hash(password):
    return generate_password_hash(password, method='pbkdf2:sha256')


def role_required(role_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Требуется авторизация', 'danger')
                return redirect(url_for('login'))
            auth = DBAuthorization.query.get(session['user_id'])
            if not auth or not auth.has_role(role_name):
                flash('Доступ запрещен. Недостаточно прав.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def admin_required(f):
    return role_required('admin')(f)


def dispatcher_required(f):
    return role_required('dispatcher')(f)


def get_user_roles():
    if 'user_id' not in session:
        return []
    auth = DBAuthorization.query.get(session['user_id'])
    return [ur.role.name for ur in auth.user_roles] if auth else []


# МАРШРУТЫ (МАРШРУТ НА index.html)
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    transports = Transport.query.all()
    form = BookingForm()

    auth = DBAuthorization.query.get(session['user_id'])
    if auth and auth.employee:
        employee = auth.employee
        form.surname.data = employee.surname
        form.firstname.data = employee.firstname
        form.secondname.data = employee.secondname or ''
        form.department.data = employee.department
        form.job_title.data = employee.job_title

    # ЗАГРУЗКА УВЕДОМЛЕНИЙ ДЛЯ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ
    notifications = Notification.query.filter_by(
        user_id=session['user_id'],
        is_read=False
    ).order_by(
        Notification.created_at.desc()
    ).limit(5).all()

    user_roles = get_user_roles()
    return render_template('index.html',
                           transports=transports,
                           form=form,
                           notifications=notifications,
                           logged_in=True,
                           is_admin='admin' in user_roles,
                           is_dispatcher='dispatcher' in user_roles)


# ПРОВЕРЯЕМ НАКЛАДЫВАЕТСЯ ЛИ ВРЕМЯ БРОНИ НА ДРУГОЕ
@app.route('/api/check_booking_overlap', methods=['POST'])
def api_check_booking_overlap():
    try:
        data = request.get_json()
        transport_id = data['transport_id']
        start_time = datetime.strptime(data['start_time'], '%Y-%m-%d %H:%M:%S')
        end_time = datetime.strptime(data['end_time'], '%Y-%m-%d %H:%M:%S')
        exclude_request_id = data.get('exclude_request_id')

        is_overlapping = check_booking_overlap(transport_id, start_time, end_time, exclude_request_id)
        return jsonify({'overlap': is_overlapping})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# МАРШРУТ АВТОРИЗАЦИИ
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))

    form = LoginForm()
    if request.method == 'POST' and form.validate_on_submit():
        login = form.login.data
        password = form.password.data

        auth = DBAuthorization.query.filter_by(login=login).first()
        if auth:
            try:
                if check_password_hash(auth.password_hash, password):
                    session['user_id'] = auth.auth_id
                    session['user_login'] = auth.login

                    # Уведомление для администратора о входе пользователя
                    admin_users = DBAuthorization.query.join(UserRole).join(Role).filter(Role.name == 'admin').all()
                    for admin in admin_users:
                        Notification.create_notification(
                            admin.auth_id,
                            f"Пользователь {auth.login} вошел в систему {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                            # ЛОГИРОВАНИЕ ВХОДА ПОЛЬЗОВАТЕЛЯ ДЛЯ АДМИНОВ
                        )
                    return redirect(url_for('index'))
                else:
                    flash('Неверный логин или пароль', 'danger')
            except ValueError as e:
                flash('Ошибка проверки пароля. Обратитесь к администратору.', 'danger')
                app.logger.error(f"Password check error for user {login}: {str(e)}")
        else:
            flash('Неверный логин или пароль', 'danger')

    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id:
        auth = DBAuthorization.query.get(user_id)
        # ЛОГИРОВАНИЕ ВЫХОДА ПООЛЬЗОВАТЕЛЯ ИЗ СИСТЕМЫ ДЛЯ АДМИНОВ
        admin_users = DBAuthorization.query.join(UserRole).join(Role).filter(Role.name == 'admin').all()
        for admin in admin_users:
            Notification.create_notification(
                admin.auth_id,
                f"Пользователь {auth.login} вышел из системы {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )

    session.pop('user_id', None)
    session.pop('user_login', None)
    return redirect(url_for('login'))


# маршрут "добавить пользователя"
@app.route('/admin/add_user', methods=['GET', 'POST'])
@admin_required
def add_user():
    form = AddUserForm()
    roles = Role.query.all()

    if request.method == 'POST' and form.validate_on_submit():
        try:
            employee = Employee(
                firstname=form.firstname.data,
                secondname=form.secondname.data,
                surname=form.surname.data,
                email=form.email.data,
                department=form.department.data,
                job_title=form.job_title.data
            )
            db.session.add(employee)
            db.session.flush()

            auth = DBAuthorization(
                employee_id=employee.employee_id,
                login=form.login.data,
                password_hash=create_password_hash(form.password.data)
            )
            db.session.add(auth)
            db.session.flush()

            selected_roles = request.form.getlist('roles')
            for role_id in selected_roles:
                user_role = UserRole(user_id=auth.auth_id, role_id=role_id)
                db.session.add(user_role)

            db.session.commit()

            # уведомление для админа о добавлении нового пользователя
            admin_users = DBAuthorization.query.join(UserRole).join(Role).filter(Role.name == 'admin').all()
            for admin in admin_users:
                Notification.create_notification(
                    admin.auth_id,
                    f"Добавлен новый пользователь: {form.surname.data} {form.firstname.data} (логин: {form.login.data})"
                )

            flash('Пользователь успешно добавлен', 'success')
            return redirect(url_for('manage_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении пользователя: {str(e)}', 'danger')

    user_roles = get_user_roles()
    return render_template('add_user.html',
                           form=form,
                           roles=roles,
                           logged_in=True,
                           is_admin='admin' in user_roles)


# управление пользователями
@app.route('/admin/manage_users')
@admin_required
def manage_users():
    users_data = db.session.query(Employee, DBAuthorization).join(
        DBAuthorization, Employee.employee_id == DBAuthorization.employee_id
    ).all()

    users = []
    for employee, auth in users_data:
        roles = [ur.role.name for ur in auth.user_roles]
        users.append({
            'employee': employee,
            'auth': auth,
            'roles': ', '.join(roles) if roles else 'Нет ролей'
        })

    user_roles = get_user_roles()
    return render_template('manage_users.html',
                           users=users,
                           logged_in=True,
                           is_admin='admin' in user_roles)


@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    auth = DBAuthorization.query.get_or_404(user_id)
    form = EditUserForm()
    roles = Role.query.all()
    user_roles = [ur.role_id for ur in auth.user_roles]

    if request.method == 'GET':
        form.firstname.data = auth.employee.firstname
        form.secondname.data = auth.employee.secondname
        form.surname.data = auth.employee.surname
        form.email.data = auth.employee.email  # Добавлено поле email
        form.department.data = auth.employee.department
        form.job_title.data = auth.employee.job_title
        form.login.data = auth.login

    if request.method == 'POST' and form.validate_on_submit():
        try:
            auth.employee.firstname = form.firstname.data
            auth.employee.secondname = form.secondname.data
            auth.employee.surname = form.surname.data
            auth.employee.email = form.email.data  # Добавлено поле email
            auth.employee.department = form.department.data
            auth.employee.job_title = form.job_title.data
            auth.login = form.login.data

            UserRole.query.filter_by(user_id=auth.auth_id).delete()
            selected_roles = request.form.getlist('roles')
            for role_id in selected_roles:
                user_role = UserRole(user_id=auth.auth_id, role_id=role_id)
                db.session.add(user_role)

            db.session.commit()

            # логирование для админа, если меняли данные пользователя
            admin_users = DBAuthorization.query.join(UserRole).join(Role).filter(Role.name == 'admin').all()
            for admin in admin_users:
                Notification.create_notification(
                    admin.auth_id,
                    f"Изменены данные пользователя: {form.surname.data} {form.firstname.data} (логин: {form.login.data})"
                )

            flash('Пользователь успешно обновлен', 'success')
            return redirect(url_for('manage_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении пользователя: {str(e)}', 'danger')

    user_roles = get_user_roles()
    return render_template('edit_user.html',
                           form=form,
                           user=auth,
                           roles=roles,
                           user_roles=user_roles,
                           logged_in=True,
                           is_admin='admin' in user_roles)


@app.route('/admin/change_password/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def change_password(user_id):
    auth = DBAuthorization.query.get_or_404(user_id)
    form = ChangePasswordForm()

    # для админов убираем проверку старого пароля
    form.old_password.validators = [validators.Optional()]

    if request.method == 'POST' and form.validate_on_submit():
        try:

            if form.old_password.data and not check_password_hash(auth.password_hash, form.old_password.data):
                flash('Неверный текущий пароль', 'danger')
                return redirect(url_for('change_password', user_id=user_id))

            auth.password_hash = create_password_hash(form.new_password.data)
            db.session.commit()

            # логирование о смене пароля для админов
            admin_users = DBAuthorization.query.join(UserRole).join(Role).filter(Role.name == 'admin').all()
            current_admin = DBAuthorization.query.get(session['user_id'])

            for admin in admin_users:
                Notification.create_notification(
                    admin.auth_id,
                    f"Администратор {current_admin.login} изменил пароль пользователя {auth.login} ({auth.employee.surname} {auth.employee.firstname})"
                )

            # логирование для пользователя, если ему поменяли пароль
            Notification.create_notification(
                auth.auth_id,
                f"Администратор {current_admin.login} изменил ваш пароль"
            )

            flash('Пароль успешно изменен', 'success')
            return redirect(url_for('manage_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при изменении пароля: {str(e)}', 'danger')

    user_roles = get_user_roles()
    return render_template('change_password.html',
                           form=form,
                           user=auth,
                           logged_in=True,
                           is_admin='admin' in user_roles)


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    try:
        auth = DBAuthorization.query.get_or_404(user_id)
        login = auth.login
        surname = auth.employee.surname
        firstname = auth.employee.firstname

        # First delete all notifications for this user
        Notification.query.filter_by(user_id=auth.auth_id).delete()

        # Then delete user roles
        UserRole.query.filter_by(user_id=auth.auth_id).delete()
        db.session.delete(auth)

        other_auth = DBAuthorization.query.filter_by(employee_id=auth.employee_id).first()
        if not other_auth:
            db.session.delete(auth.employee)

        db.session.commit()

        # Notification to admins about user deletion
        admin_users = DBAuthorization.query.join(UserRole).join(Role).filter(Role.name == 'admin').all()
        for admin in admin_users:
            Notification.create_notification(
                admin.auth_id,
                f"Удален пользователь: {surname} {firstname} (логин: {login})"
            )

        flash('Пользователь успешно удален', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении пользователя: {str(e)}', 'danger')

    return redirect(url_for('manage_users'))


# маршруты для пользователей с ролью dispatcher
@app.route('/dispatcher/requests')
@dispatcher_required
def dispatcher_requests():
    requests_data = db.session.query(
        Request,
        Employee,
        Transport,
        Approval
    ).join(
        Employee, Request.employee_id == Employee.employee_id
    ).join(
        Transport, Request.transport_id == Transport.transport_id
    ).outerjoin(
        Approval, Request.request_id == Approval.request_id
    ).order_by(
        Request.request_datetime.desc()
    ).all()

    requests = []
    for req, emp, trans, appr in requests_data:
        # определяем приоритетность статусов заявки
        if req.is_canceled:
            status = 'Canceled'
        else:
            status = appr.approval_status if appr else 'Pending'

        requests.append({
            'id': req.request_id,
            'employee': f"{emp.surname} {emp.firstname} {emp.secondname or ''}",
            'transport': trans.tsname,
            'purpose': req.purpose,
            'start_time': req.booking_datetime.strftime('%d.%m.%Y %H:%M'),
            'end_time': req.booking_end.strftime('%d.%m.%Y %H:%M'),
            'status': status,
            'is_canceled': req.is_canceled,
            'request_time': req.request_datetime.strftime('%d.%m.%Y %H:%M'),
            'comment': appr.comment if appr else None,
            'has_attachment': bool(req.attachment_data)
        })

    # счетчик статистики по заявкам
    total = len(requests)
    approved = len([r for r in requests if r['status'] == 'Approved'])
    pending = len([r for r in requests if r['status'] == 'Pending'])
    rejected = len([r for r in requests if r['status'] == 'Rejected'])
    canceled = len([r for r in requests if r['is_canceled']])

    user_roles = get_user_roles()
    return render_template('dispatcher_requests.html',
                           requests=requests,
                           total=total,
                           approved=approved,
                           pending=pending,
                           rejected=rejected,
                           canceled=canceled,
                           logged_in=True,
                           is_dispatcher='dispatcher' in user_roles)


@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    if 'user_id' not in session:
        return jsonify({'error': 'Требуется авторизация'}), 401

    notifications = Notification.query.filter_by(
        user_id=session['user_id']
    ).order_by(
        Notification.created_at.desc()
    ).limit(5).all()

    result = [{
        'id': n.notification_id,
        'message': n.message,
        'created_at': n.created_at.isoformat(),
        # ISO формат для времени, но время все равно отображается по-уродски, не знаю как исправить
        'is_read': n.is_read
    } for n in notifications]

    return jsonify({'notifications': result})


@app.route('/notifications')
def notifications_page():
    if 'user_id' not in session:
        flash('Требуется авторизация', 'danger')
        return redirect(url_for('login'))

    user_roles = get_user_roles()
    return render_template('notifications.html',
                           logged_in=True,
                           is_admin='admin' in user_roles,
                           is_dispatcher='dispatcher' in user_roles)


@app.route('/dispatcher/request/<int:request_id>', methods=['GET', 'POST'])
@dispatcher_required
def dispatcher_request_detail(request_id):
    # перевод статусов заявки на русский
    STATUS_TRANSLATIONS = {
        'Approved': 'Одобрено',
        'Rejected': 'Отклонено',
        'Pending': 'На рассмотрении',
        'Canceled': 'Отменено'
    }

    request_data = db.session.query(
        Request,
        Employee,
        Transport,
        Approval
    ).join(
        Employee, Request.employee_id == Employee.employee_id
    ).join(
        Transport, Request.transport_id == Transport.transport_id
    ).join(
        Approval, Request.request_id == Approval.request_id
    ).filter(
        Request.request_id == request_id
    ).first()

    if not request_data:
        flash('Заявка не найдена', 'danger')
        return redirect(url_for('dispatcher_requests'))

    req, emp, trans, appr = request_data

    if req.is_canceled:
        flash('Эта заявка была отменена и не может быть изменена', 'warning')
        return redirect(url_for('dispatcher_requests'))

    # проверяем наличие файла
    has_attachment = req.attachment_data is not None

    form = RequestStatusForm()
    time_form = EditTimeForm()

    if request.method == 'GET':
        form.status.data = appr.approval_status
        form.comment.data = appr.comment
        time_form.booking_datetime.data = req.booking_datetime
        time_form.booking_end.data = req.booking_end

    if request.method == 'POST':
        # Определяем, какая форма была отправлена
        if 'status_submit' in request.form:
            # Обработка изменения статуса
            if form.validate_on_submit():
                try:
                    new_transport_id = form.transport_id.data if form.transport_id.data != 0 else req.transport_id

                    # проверяем доступность транспорта
                    if new_transport_id != req.transport_id:
                        new_transport = Transport.query.get(new_transport_id)
                        if not new_transport or not new_transport.is_available:
                            flash('Невозможно назначить этот транспорт: он недоступен', 'danger')
                            return redirect(url_for('dispatcher_request_detail', request_id=request_id))

                    # если статус меняется на одобрено или транспорт изменен
                    if form.status.data == 'Approved' or new_transport_id != req.transport_id:
                        # проверяем наложения для нового транспорта
                        if check_booking_overlap(new_transport_id, req.booking_datetime, req.booking_end,
                                                 req.request_id):
                            flash('Невозможно одобрить заявку: транспорт уже забронирован на это время', 'danger')
                            return redirect(url_for('dispatcher_request_detail', request_id=request_id))

                    old_status = appr.approval_status
                    appr.approval_status = form.status.data
                    appr.approver_id = session['user_id']
                    appr.approval_date = datetime.now()
                    appr.comment = form.comment.data

                    if form.transport_id.data and form.transport_id.data != 0:
                        req.transport_id = form.transport_id.data
                        new_transport = Transport.query.get(form.transport_id.data)
                        if new_transport:
                            trans = new_transport

                    db.session.commit()

                    # логи для пользователя об изменении статуса заявки
                    if old_status != form.status.data:
                        # русский перевод статуса в уведомлении
                        russian_status = STATUS_TRANSLATIONS.get(form.status.data, form.status.data)
                        Notification.create_notification(
                            req.employee.auth[0].auth_id,
                            f"Статус вашей заявки изменен на: \"{russian_status}\""
                        )

                        # Уведомление пользователю
                        Notification.create_notification(
                            req.employee.auth[0].auth_id,
                            f"Статус вашей заявки изменен на: \"{russian_status}\""
                        )

                        # Отправка email пользователю
                        if req.employee.email:
                            user_email_subject = "Изменение статуса вашей заявки"
                            user_email_message = (
                                f"Статус вашей заявки на транспорт {trans.tsname} был изменен.\n\n"
                                f"Новый статус: {russian_status}\n"
                                f"Дата/время: {req.booking_datetime.strftime('%d.%m.%Y %H:%M')}\n"
                                f"Комментарий диспетчера: {form.comment.data if form.comment.data else 'нет'}\n\n"
                                f"Вы можете проверить детали заявки в системе."
                            )
                            if not send_email(req.employee.email, user_email_subject, user_email_message):
                                app.logger.error(f"Не удалось отправить email пользователю {req.employee.email}")

                    flash('Заявка успешно обновлена', 'success')
                    return redirect(url_for('dispatcher_request_detail', request_id=request_id))
                except Exception as e:
                    db.session.rollback()
                    flash(f'Ошибка при обновлении заявки: {str(e)}', 'danger')

        elif 'time_submit' in request.form:
            # Обработка изменения времени
            try:
                # Получаем данные из формы напрямую из request.form
                booking_datetime_str = request.form.get('booking_datetime')
                booking_end_str = request.form.get('booking_end')

                if not booking_datetime_str or not booking_end_str:
                    flash('Необходимо указать время начала и окончания', 'danger')
                    return redirect(url_for('dispatcher_request_detail', request_id=request_id))

                # Парсим даты из формата datetime-local
                new_start_time = datetime.strptime(booking_datetime_str, '%Y-%m-%dT%H:%M')
                new_end_time = datetime.strptime(booking_end_str, '%Y-%m-%dT%H:%M')

                # Валидация времени
                #if new_start_time < datetime.now() - timedelta(minutes=5):
                #    flash('Нельзя выбрать дату и время раньше текущего момента', 'danger')
                 #   return redirect(url_for('dispatcher_request_detail', request_id=request_id))

                if new_end_time <= new_start_time:
                    flash('Время окончания должно быть позже времени начала', 'danger')
                    return redirect(url_for('dispatcher_request_detail', request_id=request_id))

                # Проверяем наложения по времени
                if check_booking_overlap(req.transport_id, new_start_time, new_end_time, req.request_id):
                    flash('Невозможно изменить время: транспорт уже забронирован на это время', 'danger')
                    return redirect(url_for('dispatcher_request_detail', request_id=request_id))

                # Обновляем время
                req.booking_datetime = new_start_time
                req.booking_end = new_end_time
                req.duration = new_end_time - new_start_time

                db.session.commit()

                # Уведомление пользователю об изменении времени
                Notification.create_notification(
                    req.employee.auth[0].auth_id,
                    f"Время вашей заявки на транспорт {trans.tsname} изменено: {new_start_time.strftime('%d.%m.%Y %H:%M')} - {new_end_time.strftime('%d.%m.%Y %H:%M')}"
                )

                # Уведомление диспетчерам
                dispatchers = DBAuthorization.query.join(UserRole).join(Role).filter(Role.name == 'dispatcher').all()
                current_dispatcher = DBAuthorization.query.get(session['user_id'])
                for dispatcher in dispatchers:
                    if dispatcher.auth_id != current_dispatcher.auth_id:
                        Notification.create_notification(
                            dispatcher.auth_id,
                            f"Диспетчер {current_dispatcher.login} изменил время заявки #{request_id}"
                        )

                flash('Время заявки успешно изменено', 'success')
                return redirect(url_for('dispatcher_request_detail', request_id=request_id))
            except ValueError as e:
                flash('Неверный формат даты и времени', 'danger')
                return redirect(url_for('dispatcher_request_detail', request_id=request_id))
            except Exception as e:
                db.session.rollback()
                flash(f'Ошибка при изменении времени: {str(e)}', 'danger')
                return redirect(url_for('dispatcher_request_detail', request_id=request_id))

    # проверяем пересечения по времени для отображения предупреждения
    is_overlapping = check_booking_overlap(req.transport_id, req.booking_datetime, req.booking_end, req.request_id)

    user_roles = get_user_roles()
    return render_template('dispatcher_request_detail.html',
                           request=req,
                           employee=emp,
                           transport=trans,
                           approval=appr,
                           form=form,
                           time_form=time_form,
                           has_attachment=has_attachment,
                           is_overlapping=is_overlapping,
                           logged_in=True,
                           is_dispatcher='dispatcher' in user_roles)


@app.route('/api/has_new_notifications')
def has_new_notifications():
    if 'user_id' not in session:
        return jsonify({'error': 'Требуется авторизация'}), 401

    # проверяем наличие непрочитанных уведомлений
    count = Notification.query.filter_by(
        user_id=session['user_id'],
        is_read=False
    ).count()

    return jsonify({'has_new': count > 0})


@app.route('/api/notifications_count', methods=['GET'])
def notifications_count():
    if 'user_id' not in session:
        return jsonify({'error': 'Требуется авторизация'}), 401

    count = Notification.query.filter_by(
        user_id=session['user_id'],
        is_read=False
    ).count()

    return jsonify({'count': count})


@app.route('/change_password', methods=['GET', 'POST'])
def change_own_password():
    if 'user_id' not in session:
        flash('Требуется авторизация', 'danger')
        return redirect(url_for('login'))

    auth = DBAuthorization.query.get(session['user_id'])
    form = ChangePasswordForm()

    if request.method == 'POST' and form.validate_on_submit():
        try:
            # проверяем старый пароль
            if not check_password_hash(auth.password_hash, form.old_password.data):
                flash('Неверный текущий пароль', 'danger')
                return redirect(url_for('change_own_password'))

            # проверяем, что новый пароль отличается от старого
            if check_password_hash(auth.password_hash, form.new_password.data):
                flash('Новый пароль должен отличаться от текущего', 'danger')
                return redirect(url_for('change_own_password'))

            auth.password_hash = create_password_hash(form.new_password.data)
            db.session.commit()

            # уведомление для администраторов о смене пароля пользователем
            admin_users = DBAuthorization.query.join(UserRole).join(Role).filter(Role.name == 'admin').all()
            for admin in admin_users:
                Notification.create_notification(
                    admin.auth_id,
                    f"Пользователь {auth.login} ({auth.employee.surname} {auth.employee.firstname}) изменил свой пароль"
                )

            # уведомление для самого пользователя
            Notification.create_notification(
                auth.auth_id,
                "Ваш пароль был успешно изменен"
            )

            flash('Пароль успешно изменен', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при изменении пароля: {str(e)}', 'danger')

    user_roles = get_user_roles()
    return render_template('change_password.html',
                           form=form,
                           user=auth,
                           logged_in=True,
                           is_admin='admin' in user_roles,
                           is_dispatcher='dispatcher' in user_roles)


@app.route('/dispatcher/transport', methods=['GET', 'POST'])
@dispatcher_required
def dispatcher_transport():
    if request.method == 'POST':
        # обработка добавления нового транспорта
        if 'add_transport' in request.form:
            tsname = request.form['tsname']
            brand = request.form['brand']
            model = request.form['model']
            tsnumber = request.form['tsnumber']
            requires_attachment = 'requires_attachment' in request.form

            new_transport = Transport(
                tsname=tsname,
                brand=brand,
                model=model,
                tsnumber=tsnumber,
                requires_attachment=requires_attachment
            )
            db.session.add(new_transport)
            db.session.commit()

            # уведомление для диспетчеров о добавлении транспорта
            dispatchers = DBAuthorization.query.join(UserRole).join(Role).filter(Role.name == 'dispatcher').all()
            for dispatcher in dispatchers:
                Notification.create_notification(
                    dispatcher.auth_id,
                    f"Добавлен новый транспорт: {tsname} {brand} {model} ({tsnumber})"
                )

            flash('Транспорт успешно добавлен', 'success')
            return redirect(url_for('dispatcher_transport'))

        # обработка удаления транспорта
        transport_id = request.form.get('transport_id')
        if transport_id:
            if 'delete_transport' in request.form:
                transport = Transport.query.get(transport_id)
                if transport:
                    try:
                        # находим все рабочие связанные заявки
                        related_requests = Request.query.filter_by(transport_id=transport_id).all()
                        for req in related_requests:
                            # удаляем связанные approval
                            Approval.query.filter_by(request_id=req.request_id).delete()
                            # удаляем саму заявку
                            db.session.delete(req)

                        db.session.delete(transport)
                        db.session.commit()

                        # уведомление для диспетчеров об удалении транспорта
                        dispatchers = DBAuthorization.query.join(UserRole).join(Role).filter(
                            Role.name == 'dispatcher').all()
                        for dispatcher in dispatchers:
                            Notification.create_notification(
                                dispatcher.auth_id,
                                f"Удален транспорт: {transport.tsname} {transport.brand} {transport.model} ({transport.tsnumber})"
                            )

                        flash('Транспорт успешно удален', 'success')
                    except Exception as e:
                        db.session.rollback()
                        flash(f'Ошибка при удалении транспорта: {str(e)}', 'danger')
                return redirect(url_for('dispatcher_transport'))

            # обработка изменения статуса транспорта
            if 'change_status' in request.form:
                transport = Transport.query.get(transport_id)
                if transport:
                    new_status = request.form.get('new_status') == 'True'
                    transport.is_available = new_status
                    db.session.commit()

                    # уведомление для диспетчеров об изменении статуса транспорта
                    dispatchers = DBAuthorization.query.join(UserRole).join(Role).filter(
                        Role.name == 'dispatcher').all()
                    for dispatcher in dispatchers:
                        Notification.create_notification(
                            dispatcher.auth_id,
                            f"Изменен статус транспорта {transport.tsname}: {'Доступен' if new_status else 'Недоступен'}"
                        )

                    flash('Статус транспорта успешно изменен', 'success')
                return redirect(url_for('dispatcher_transport'))

    # получаем весь транспорт из базы данных
    transports = Transport.query.order_by(Transport.tsname).all()
    user_roles = get_user_roles()
    return render_template('dispatcher_transport.html',
                           transports=transports,
                           logged_in=True,
                           is_dispatcher='dispatcher' in user_roles)


@app.route('/api/check_transport_available', methods=['POST'])
def check_transport_available():
    try:
        data = request.get_json()
        transport_id = data['transport_id']
        transport = Transport.query.get(transport_id)
        if not transport:
            return jsonify({'error': 'Transport not found'}), 404
        return jsonify({'is_available': transport.is_available})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/request/<int:request_id>/attachment')
def download_attachment(request_id):
    app.logger.info(f"Запрос файла для заявки {request_id}")
    if 'user_id' not in session:
        flash('Требуется авторизация', 'danger')
        return redirect(url_for('login'))

    request_obj = Request.query.get_or_404(request_id)
    auth = DBAuthorization.query.get(session['user_id'])

    if not auth.has_role('dispatcher') and request_obj.employee_id != auth.employee_id:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    if not request_obj.attachment_data:
        flash('Файл не найден', 'danger')
        return redirect(url_for('index'))

    filename = 'attachment'
    if request_obj.attachment_filename:
        try:
            if isinstance(request_obj.attachment_filename, (memoryview, bytes)):
                filename = secure_filename(request_obj.attachment_filename.tobytes().decode('utf-8'))
            else:
                filename = secure_filename(str(request_obj.attachment_filename))
        except:
            filename = 'attachment'

    mimetype = 'application/octet-stream'
    if request_obj.attachment_mimetype:
        try:
            if isinstance(request_obj.attachment_mimetype, (memoryview, bytes)):
                mimetype = request_obj.attachment_mimetype.tobytes().decode('utf-8')
            else:
                mimetype = str(request_obj.attachment_mimetype)
        except:
            mimetype = 'application/octet-stream'

    file_data = bytes(request_obj.attachment_data)

    download = request.args.get('download', 'false').lower() == 'true'

    if not download and (mimetype.startswith('image/') or mimetype == 'application/pdf'):
        return Response(
            file_data,
            mimetype=mimetype,
            headers={'Content-Disposition': f'inline; filename="{filename}"'}
        )

    return Response(
        file_data,
        mimetype=mimetype,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@app.route('/api/requests')
def get_requests():
    try:
        if 'user_id' not in session:
            return jsonify({'error': 'Требуется авторизация'}), 401

        auth = DBAuthorization.query.get(session['user_id'])
        if not auth:
            return jsonify({'error': 'Пользователь не найден'}), 404

        base_query = db.session.query(
            Request,
            Employee,
            Transport,
            Approval
        ).join(
            Employee, Request.employee_id == Employee.employee_id
        ).join(
            Transport, Request.transport_id == Transport.transport_id
        ).outerjoin(
            Approval, Request.request_id == Approval.request_id
        )

        if auth.has_role('dispatcher'):
            requests_data = base_query.order_by(
                Request.request_datetime.desc()
            ).limit(20).all()
        else:
            requests_data = base_query.filter(
                Request.employee_id == auth.employee_id
            ).order_by(
                Request.request_datetime.desc()
            ).limit(20).all()

        result = []
        for req, emp, trans, appr in requests_data:
            status = 'Canceled' if req.is_canceled else (appr.approval_status if appr else 'Pending')

            result.append({
                'id': req.request_id,
                'employee': f"{emp.surname} {emp.firstname} {emp.secondname or ''}",
                'department': emp.department,
                'job_title': emp.job_title,
                'transport': f"{trans.tsname} {trans.brand} {trans.model} ({trans.tsnumber})",
                'purpose': req.purpose,
                'phone': req.phone_number,
                'from': req.loc_from,
                'to': req.loc_to,
                'start_time': req.booking_datetime.strftime('%d.%m.%Y %H:%M'),
                'end_time': req.booking_end.strftime('%d.%m.%Y %H:%M'),
                'status': status,
                'comment': appr.comment if appr else None,
                'request_time': req.request_datetime.strftime('%d.%m.%Y %H:%M'),
                'has_attachment': bool(req.attachment_data),
                'is_canceled': req.is_canceled
            })

        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error loading requests: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/all_notifications')
def get_all_notifications():
    if 'user_id' not in session:
        return jsonify({'error': 'Требуется авторизация'}), 401

    notifications = Notification.query.filter_by(
        user_id=session['user_id']
    ).order_by(
        Notification.created_at.desc()
    ).all()

    result = [{
        'id': n.notification_id,
        'message': n.message,
        'created_at': n.created_at.strftime('%d.%m.%Y %H:%M'),
        'is_read': n.is_read
    } for n in notifications]

    return jsonify(result)


@app.route('/api/create_request', methods=['POST'])
def create_request():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Требуется авторизация'}), 401

        data = request.form
        auth = DBAuthorization.query.get(session['user_id'])
        employee = auth.employee

        transport_id = int(data['transport_id'])
        transport = Transport.query.get(transport_id)
        start_time = datetime.strptime(data['booking_datetime'], '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(data['booking_end'], '%Y-%m-%dT%H:%M')


        use_without_kmu = 'use_without_kmu' in data and data['use_without_kmu'] == 'true'


        duration = end_time - start_time


        # if start_time < min_start_time:
        #     return jsonify({
        #         'success': False,
        #         'message': 'Нельзя выбрать время начала раньше чем через 5 минут от текущего момента'
        #     }), 400

        if end_time <= start_time:
            return jsonify({
                'success': False,
                'message': 'Время окончания должно быть позже времени начала'
            }), 400

        attachment_data = None
        attachment_filename = None
        attachment_mimetype = None

        if not use_without_kmu and 'attachment' in request.files:
            file = request.files['attachment']
            if file.filename != '' and allowed_file(file.filename):
                attachment_filename = str(secure_filename(file.filename))
                attachment_data = file.read()
                attachment_mimetype = str(file.content_type)

        booking = Request(
            employee_id=employee.employee_id,
            transport_id=transport_id,
            phone_number=data['phone_number'],
            purpose=data['purpose'],
            attachment_filename=attachment_filename,
            attachment_data=attachment_data,
            attachment_mimetype=attachment_mimetype,
            booking_datetime=start_time,
            booking_end=end_time,
            duration=duration,
            loc_from=data['loc_from'],
            loc_to=data['loc_to'],
            request_datetime=datetime.now(),
            use_without_kmu=use_without_kmu
        )
        db.session.add(booking)
        db.session.flush()

        approval = Approval(
            request_id=booking.request_id,
            approval_status='Pending'
        )
        db.session.add(approval)

        db.session.commit()

        Notification.create_notification(auth.auth_id,
                                         f"Вы отправили заявку на транспорт {transport.tsname} на {start_time.strftime('%d.%m.%Y %H:%M')}")

        # Уведомление для диспетчеров
        dispatchers = DBAuthorization.query.join(UserRole).join(Role).filter(Role.name == 'dispatcher').all()
        for dispatcher in dispatchers:
            Notification.create_notification(
                dispatcher.auth_id,
                f"Новая заявка от {employee.surname} {employee.firstname} на транспорт {transport.tsname}"
            )

            # Отправка email диспетчеру
            if dispatcher.employee.email:
                dispatcher_email_subject = "Новая заявка в СУАТ"
                dispatcher_email_message = (
                    f"Поступила новая заявка в СУАТ:\n\n"
                    f"От: {employee.surname} {employee.firstname}\n"
                    f"Транспорт: {transport.tsname}\n"
                    f"Дата/время: {start_time.strftime('%d.%m.%Y %H:%M')}\n"
                    f"Цель: {data['purpose']}\n"
                    f"Телефон: {data['phone_number']}\n\n"
                    f"Пожалуйста, обработайте заявку в системе."
                )
                if not send_email(dispatcher.employee.email, dispatcher_email_subject, dispatcher_email_message):
                    app.logger.error(f"Не удалось отправить email диспетчеру {dispatcher.employee.email}")

        return jsonify({'success': True, 'message': 'Заявка успешно создана!'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating request: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/update_request/<int:request_id>', methods=['POST'])
def update_request(request_id):
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Требуется авторизация'}), 401

        auth = DBAuthorization.query.get(session['user_id'])
        request_obj = Request.query.get_or_404(request_id)

        if request_obj.employee_id != auth.employee_id and not auth.has_role('dispatcher'):
            return jsonify({'success': False, 'message': 'Нет прав на редактирование этой заявки'}), 403

        if request_obj.is_canceled:
            return jsonify({'success': False, 'message': 'Нельзя редактировать отмененную заявку'}), 400

        data = request.form
        transport_id = int(data.get('transport_id', request_obj.transport_id))

        booking_datetime_str = data.get('booking_datetime')
        booking_end_str = data.get('booking_end')

        if booking_datetime_str:
            start_time = datetime.strptime(booking_datetime_str, '%Y-%m-%dT%H:%M')
        else:
            start_time = request_obj.booking_datetime

        if booking_end_str:
            end_time = datetime.strptime(booking_end_str, '%Y-%m-%dT%H:%M')
        else:
            end_time = request_obj.booking_end

        # Calculate new duration
        duration = end_time - start_time

        # УДАЛЕНА ПРОВЕРКА ВРЕМЕНИ
        # if start_time < datetime.now() - timedelta(minutes=5):
        #     return jsonify({
        #         'success': False,
        #         'message': 'Нельзя выбрать дату и время раньше текущего момента'
        #     }), 400

        if end_time <= start_time:
            return jsonify({
                'success': False,
                'message': 'Время окончания должно быть позже времени начала'
            }), 400

        request_obj.transport_id = transport_id
        request_obj.phone_number = data.get('phone_number', request_obj.phone_number)
        request_obj.purpose = data.get('purpose', request_obj.purpose)
        request_obj.loc_from = data.get('loc_from', request_obj.loc_from)
        request_obj.loc_to = data.get('loc_to', request_obj.loc_to)
        request_obj.booking_datetime = start_time
        request_obj.booking_end = end_time
        request_obj.duration = duration  # Update duration here

        if 'attachment' in request.files:
            file = request.files['attachment']
            if file.filename != '' and allowed_file(file.filename):
                request_obj.attachment_filename = secure_filename(file.filename)
                request_obj.attachment_data = file.read()
                request_obj.attachment_mimetype = file.content_type

        db.session.commit()

        return jsonify({'success': True, 'message': 'Заявка успешно обновлена'})

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating request: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


# маршрут для отчетов за определенный период
@app.route('/dispatcher/reports', methods=['GET', 'POST'])
@dispatcher_required
def dispatcher_reports():
    # Default values
    requests = []
    total = approved = pending = rejected = canceled = 0
    start_date = end_date = None

    if request.method == 'POST':
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d') + timedelta(days=1)

        # Base query
        query = db.session.query(
            Request,
            Employee,
            Transport,
            Approval
        ).join(
            Employee, Request.employee_id == Employee.employee_id
        ).join(
            Transport, Request.transport_id == Transport.transport_id
        ).outerjoin(
            Approval, Request.request_id == Approval.request_id
        ).filter(
            Request.request_datetime >= start_date,
            Request.request_datetime <= end_date
        )

        # Apply sorting if needed
        sort_column = request.form.get('sort_column', 'request_datetime')
        sort_direction = request.form.get('sort_direction', 'desc')

        if sort_column == 'id':
            order_by = Request.request_id
        elif sort_column == 'employee':
            order_by = Employee.surname
        elif sort_column == 'department':
            order_by = Employee.department
        elif sort_column == 'transport':
            order_by = Transport.tsname
        elif sort_column == 'status':
            order_by = Approval.approval_status
        elif sort_column == 'created':
            order_by = Request.request_datetime
        else:
            order_by = Request.request_datetime

        if sort_direction == 'asc':
            query = query.order_by(order_by.asc())
        else:
            query = query.order_by(order_by.desc())

        requests_data = query.all()

        # Prepare data for template with statistics
        requests = []
        total = len(requests_data)
        approved = pending = rejected = canceled = 0

        for req, emp, trans, appr in requests_data:
            # Calculate status
            if req.is_canceled:
                status = 'Canceled'
                canceled += 1
            elif appr:
                status = appr.approval_status
                if status == 'Approved':
                    approved += 1
                elif status == 'Rejected':
                    rejected += 1
                else:
                    pending += 1
            else:
                status = 'Pending'
                pending += 1

            # Calculate duration in seconds from the interval
            duration_seconds = req.duration.total_seconds() if req.duration else 0

            requests.append({
                'id': req.request_id,
                'employee': f"{emp.surname} {emp.firstname} {emp.secondname or ''}",
                'department': emp.department,
                'transport': f"{trans.brand} {trans.model} ({trans.tsnumber})",
                'start_time': req.booking_datetime.strftime('%d.%m.%Y %H:%M'),
                'end_time': req.booking_end.strftime('%d.%m.%Y %H:%M'),
                'duration_seconds': duration_seconds,
                'status': status,
                'request_time': req.request_datetime.strftime('%d.%m.%Y %H:%M')
            })

    # Default date range for initial view
    if not start_date or not end_date:
        default_end = datetime.now()
        default_start = default_end - timedelta(days=7)
        start_date = default_start.strftime('%Y-%m-%d')
        end_date = default_end.strftime('%Y-%m-%d')
    else:
        start_date = start_date.strftime('%Y-%m-%d')
        end_date = (end_date - timedelta(days=1)).strftime('%Y-%m-%d')

    user_roles = get_user_roles()
    return render_template('dispatcher_reports.html',
                           requests=requests,
                           start_date=start_date,
                           end_date=end_date,
                           logged_in=True,
                           is_dispatcher='dispatcher' in user_roles,
                           total=total,
                           approved=approved,
                           pending=pending,
                           rejected=rejected,
                           canceled=canceled)

    # Default view (no filters applied)
    default_end = datetime.now()
    default_start = default_end - timedelta(days=7)

    user_roles = get_user_roles()
    return render_template('dispatcher_reports.html',
                           requests=None,
                           start_date=default_start.strftime('%Y-%m-%d'),
                           end_date=default_end.strftime('%Y-%m-%d'),
                           logged_in=True,
                           is_dispatcher='dispatcher' in user_roles,
                           total=0,
                           approved=0,
                           pending=0,
                           rejected=0,
                           canceled=0)


@app.route('/api/cancel_request/<int:request_id>', methods=['POST'])
def cancel_request(request_id):
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Требуется авторизация'}), 401

        auth = DBAuthorization.query.get(session['user_id'])
        request_obj = Request.query.get_or_404(request_id)

        if request_obj.employee_id != auth.employee_id and not auth.has_role('dispatcher'):
            return jsonify({'success': False, 'message': 'Нет прав на отмену этой заявки'}), 403

        # можно отменить заявку даже если одобрена
        request_obj.is_canceled = True
        approval = Approval.query.filter_by(request_id=request_id).first()
        if approval:
            approval.approval_status = 'Canceled'

        db.session.commit()

        # Уведомление для пользователя об отмене заявки
        Notification.create_notification(
            request_obj.employee.auth[0].auth_id,
            f"Вы отменили заявку на транспорт {request_obj.transport.tsname}"
        )

        # Уведомление для диспетчеров об отмене заявки
        dispatchers = DBAuthorization.query.join(UserRole).join(Role).filter(Role.name == 'dispatcher').all()
        for dispatcher in dispatchers:
            Notification.create_notification(
                dispatcher.auth_id,
                f"Заявка #{request_id} от {request_obj.employee.surname} отменена"
            )

        return jsonify({'success': True, 'message': 'Заявка успешно отменена'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error canceling request: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/notifications/mark_all_as_read', methods=['POST'])
def mark_all_notifications_as_read():
    if 'user_id' not in session:
        return jsonify({'error': 'Требуется авторизация'}), 401

    try:
        Notification.query.filter_by(
            user_id=session['user_id'],
            is_read=False
        ).update({'is_read': True})
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/notifications/mark_as_read', methods=['POST'])
def mark_notification_as_read():
    if 'user_id' not in session:
        return jsonify({'error': 'Требуется авторизация'}), 401

    data = request.get_json()
    if not data or 'id' not in data:
        return jsonify({'error': 'Не указан ID уведомления'}), 400

    try:
        notification = Notification.query.filter_by(
            notification_id=data['id'],
            user_id=session['user_id']
        ).first()

        if not notification:
            return jsonify({'error': 'Уведомление не найдено'}), 404

        notification.is_read = True
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error marking notification as read: {str(e)}")
        return jsonify({'error': str(e)}), 500



@app.route('/transport_table')
def transport_table():
    if 'user_id' not in session:
        flash('Требуется авторизация', 'danger')
        return redirect(url_for('login'))

    current_time = datetime.now()

    # Получаем только активные одобренные заявки с транспортом (без удаления из базы)
    bookings = db.session.query(
        Approval, Request, Transport, Employee
    ).join(
        Request, Approval.request_id == Request.request_id
    ).join(
        Transport, Request.transport_id == Transport.transport_id
    ).join(
        Employee, Request.employee_id == Employee.employee_id
    ).filter(
        Approval.approval_status == 'Approved',
        Request.is_canceled == False,
        Request.booking_end > current_time  # Только активные бронирования для отображения
    ).order_by(
        Request.booking_datetime.asc()
    ).all()

    # преобразуем результат в список словарей
    bookings_data = []
    for approval, request, transport, employee in bookings:
        bookings_data.append({
            'approval': approval,
            'request': request,
            'transport': transport,
            'employee': employee,
            'status': approval.approval_status.lower()
        })

    return render_template('transport_table.html', bookings=bookings_data)


def check_booking_overlap(transport_id, start_time, end_time, exclude_request_id=None):

    # Проверяем, что транспорт существует
    transport = Transport.query.get(transport_id)
    if not transport:
        return False

    overlapping = db.session.query(Request).join(
        Approval, Request.request_id == Approval.request_id
    ).filter(
        Request.transport_id == transport_id,
        Approval.approval_status == 'Approved',
        Request.is_canceled == False,  # Исключаем отмененные заявки
        Request.request_id != exclude_request_id if exclude_request_id else True,
        or_(
            and_(Request.booking_datetime < end_time, Request.booking_end > start_time),
        )
    ).first()

    return overlapping is not None

#определяем роли
def init_db():
    with app.app_context():
        db.create_all()

        roles = [
            ('user', 'Может только создавать заявки'),
            ('admin', 'Может управлять пользователями и назначать рол'),
            ('dispatcher', 'Может работать с заявками, менять их статус, назначать транспорт')
        ]

        for role_name, description in roles:
            if not Role.query.filter_by(name=role_name).first():
                role = Role(name=role_name, description=description)
                db.session.add(role)

        db.session.commit()
        #инициализируем спец.транспорт
        special_transports = [
            "Бортовой автомобиль с КМУ (7,2 т.)",
            "Автогидроподъемник (28 м.)",
            "Кран на пневмоходу (70 т.)",
            "Кран на колесном ходу (25 т.)"
        ]

        for transport_name in special_transports:
            if not Transport.query.filter_by(tsname=transport_name).first():
                transport = Transport(
                    tsname=transport_name,
                    brand="Спецтехника",
                    model="Специальная",
                    tsnumber="СТ000",
                    requires_attachment=True
                )
                db.session.add(transport)

        db.session.commit()

# Миграция для добавления нового поля
with app.app_context():
    try:
        # Проверяем существование столбца
        from sqlalchemy import text
        result = db.session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='request' AND column_name='use_without_kmu'"))
        if not result.fetchone():
            # Добавляем столбец если его нет
            db.session.execute(text("ALTER TABLE request ADD COLUMN use_without_kmu BOOLEAN DEFAULT FALSE"))
            db.session.commit()
            print("Миграция базы данных выполнена успешно")
    except Exception as e:
        print(f"Ошибка миграции: {e}")
        db.session.rollback()

if __name__ == '__main__':
    app.run(host='00.00.000.00', port=5000, debug=True)
    app.run(debug=True)

    backup_thread = threading.Thread(target=backup_scheduler)
    backup_thread.daemon = True
    backup_thread.start()

    init_db()
    app.run(debug=True)