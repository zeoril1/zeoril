import flask
from flask import Flask,render_template,send_from_directory,session, request
import sqlite3
import hashlib
import json

app = Flask(__name__)
conn = sqlite3.connect('resources/discord.sqlite3', check_same_thread=False)
cur = conn.cursor()
@app.route('/',methods=['post','get'])
def index():
    User = check_cookie(request.cookies.get('Auth'))
    if User != False:
        message = 'Добро пожаловать, '+User[0][1]+'!'
        return render_template('index.html', message=message)
    else:
        x=''
        form = flask.Markup('<form action="/" method="post"><p><label for="username">ID в дискорде</label><input type="text" name="ID"></p>' \
               '<p><label for="password">Пароль</label><input type="password" name="password"></p><p><input type="submit" name="login">' \
               '<a href="/register">Регистрация</a></p></form>')
        for x in request.form.items():
            y=1
        if request.method == 'POST' and x[0] == 'login':
            password = hashlib.md5(request.form.get('password').encode('utf-8')).hexdigest()
            sql = "SELECT * FROM Users WHERE ID = "+request.form.get('ID')+" and Password = '"+password+"';"
            cur.execute(sql)
            User = cur.fetchall()
            if User:
                hash_text = request.form.get('password')+'session'
                hash = hashlib.md5(hash_text.encode('utf-8')).hexdigest()
                sql = "INSERT INTO Session (ID,Hash) VALUES ("+request.form.get('ID')+", '"+str(hash)+"');"
                cur.execute(sql)
                conn.commit()
                rights = user_rights(User[0][0])
                res = flask.make_response(flask.redirect('/'))
                res.set_cookie('Auth', hash)
                res.set_cookie('Id', str(User[0][0]))
                res.set_cookie('Rights', str(rights))
                return res
            else:
                message = 'ID или пароль не верен'
                return render_template('index.html', form=form, message=message)
        else:
            return render_template('index.html', form=form)

@app.route('/register',methods=['post','get'])
def register():
    form = flask.Markup('<form action="/register" method="post"><p><label for="id">ID в дискорде</label><input type="text" name="id"></p>'
                           '<p><input value="Проверить" type="submit" name="check"></p></form>')
    message = ''
    for x in request.form.items():
        print (x[0])
    if request.method == 'POST' and x[0] == 'check':
        values = {'Id': request.form.get('id')}
        cur.execute("SELECT * FROM Users WHERE ID = :Id;", values)
        User = cur.fetchall()
        if User:
            print(User[0][3])
            if User[0][3] == None:
                message = User[0][0]
                form = flask.Markup(
                    '<form action="/register" method="post" id="reg"><input type="text" name="id" value=' + request.form.get(
                        'id') + '>'
                                '<p><label for="pass">Пароль</label><input type="text" name="pass"></p>'
                                '<p><input value="Зарегистрироваться" type="submit" name="reg"></p></form>')
                message = 'Пользователь найден и не зарегистрирован'
                return render_template('register.html', form=form, message=message)
            else:
                message = 'Пользователь найден используйте пароль для входа'
                return render_template('register.html', message=message)

        else:
            message = 'Пользователь не найден, зарегистрируйтесь через дискорд командой !reg'
            return render_template('register.html', message=message)
    elif request.method == 'POST' and x[0] == 'reg':
        password = hashlib.md5(request.form.get('pass').encode('utf-8')).hexdigest()
        values = {'ID': request.form.get('id'), 'Name': request.form.get('name'), 'Song': 'None','Password': password}
        cur.execute("INSERT INTO Users (ID,Name,Song,Password) VALUES (:ID, :Name, :Song, :Password);", values)
        conn.commit()
        message = 'Регистрация успешно выполнена'
        return render_template('register.html', message=message)
    else:
        return render_template('register.html', form=form)

@app.route('/logs')
def logs():
    logger = open('resources/logs.txt', 'r', encoding="ISO-8859-1").read()
    return render_template('logs.html', to_configs=logger)

@app.route('/song')
def song():
    music_welcome = music()
    return render_template('song.html', to_music=music_welcome)

@app.route('/music/<path:filename>')
def download_file(filename):
    print (filename)
    return send_from_directory('music/', filename)

def music():
    cur.execute("SELECT * FROM Users;")
    music_welcome = cur.fetchall()
    return music_welcome

def check_cookie(hash):
    if hash:
        sql = "SELECT Users.*, Session.ID FROM Users, Session WHERE Users.ID = Session.ID and Session.Hash = '"+hash+"';"
        cur.execute(sql)
        User = cur.fetchall()
        return User
    else:
        return False

def user_rights(id_user):
    if id_user:
        sql = "SELECT Rights.* FROM Rights, Users_rights WHERE Users_rights.ID_user = " + str(id_user) + " AND Rights.ID = Users_rights.ID_right;"
        cur.execute(sql)
        rights = cur.fetchall()
        return rights
    else:
        return False

if __name__ == '__main__':
    app.run(port=80, host='0.0.0.0')