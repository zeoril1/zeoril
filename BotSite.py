import flask
from flask import Flask,render_template,send_from_directory,redirect, request
import sqlite3
import hashlib
import json
import os

app = Flask(__name__)
conn = sqlite3.connect('resources/discord.sqlite3', check_same_thread=False)
cur = conn.cursor()

@app.route('/',methods=['post','get'])
def index():
    User = check_cookie(request.cookies.get('Auth'))
    Session = check_session(request.cookies.get('Id'))
    if Session != False:
        info = get_info(' WHERE ID = '+request.cookies.get('Id'))
        rights = user_rights(request.cookies.get('Id'))
        right = False
        if rights != False:
            for le in rights:
                if ('Admin' in le) == True or ('Music' in le) == True:
                    right = True
                    break
        if request.method == 'GET' and request.args.getlist('Select'):
            if right == True:
                music ='<form method="GET" action="/"> <select name="new_music" class="form-select">'
                for root, dirs, files in os.walk("music"):
                    for filename in files:
                        music += '<option>'+filename+'</option>'
                music += '</select><button type="submit" name="Save" class="btn btn-primary">Сохранить</button></form>'
            else:
                return redirect('/',code=403)
        elif request.method == 'GET' and request.args.getlist('Save'):
            if right == True:
                save_new_music(info[0][1], request.args.getlist('new_music')[0])
                return redirect('/')
            else:
                return redirect('/',code=403)
        else:
            if right == True:
                music ='<audio src="music/' + info[0][2] + '" controls class="h-100"></audio><form method="GET" action="/"> <button type="submit" name="Select" class="btn btn-primary">Изменить звук</button></form>'
            else:
                music = '<audio src="music/' + info[0][2] + '" controls></audio>'
        message = flask.Markup('<div class="container"><div class="row p-2 mb-2 mt-2 bg-dark text-white" >'
                               '<div class="col d-flex justify-content-center"><label for="username">ID в дискорде: </label><label for="username">'+str(info[0][0])+'</label></div></div>'
                               '<div class="row p-2 mb-2 bg-secondary text-white">'
                               '<div class="col d-flex justify-content-center border-end border-1"><label for="username">Имя в дискорде: </label><label for="username">'+str(info[0][1])+'</label></div>'
                               '<div class="col d-flex justify-content-center border-start border-1"><label for="username">Имя в игре: </label><label for="username">'+str(info[0][4])+'</label></div></div>'
                               '<div class="row p-2 mb-2 bg-secondary text-white"><div class="col d-flex justify-content-center">'
                               +music+
                               '</div></div></div>')
        header_message = 'Добро пожаловать, '+User[0][1]+'!'
        header = flask.Markup('<h6>' + header_message + '</h6><form action="/exit" method="POST">'
                                                 '<input type="hidden" name="exit" value="'+request.cookies.get('Id')+'">'
                                                 ' <input type="submit" class="btn btn-warning" value="Выйти"></form>')
        return render_template('index.html', session=header, message= message)
    else:
        x=''
        header = flask.Markup(open('templates/header_out.html', encoding="utf-8").read())
        form = flask.Markup(open('templates/login.html', encoding="utf-8").read())
        register = flask.Markup(open('templates/reg.html', encoding="utf-8").read())
        for x in request.form.items():
            y=1
        if request.method == 'POST' and x[0] == 'login':
            password = hashlib.md5(request.form.get('password').encode('utf-8')).hexdigest()
            sql = "SELECT * FROM Users WHERE ID = "+request.form.get('ID')+" and Password = '"+password+"';"
            cur.execute(sql)
            User = cur.fetchall()
            if User:
                hash_text = request.form.get('password')+str(User[0][0])
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
                return render_template('index.html', login=form, message=message, register = register)
        else:
            return render_template('index.html', login=form, register = register,  session=header)

@app.route('/register',methods=['post','get'])
def register():
    id = request.form.get('ID')
    cur.execute("SELECT * FROM Users WHERE ID ="+id)
    User = cur.fetchall()
    if User:
        if User[0][3] == None:
            password = hashlib.md5(request.form.get('password').encode('utf-8')).hexdigest()
            values = {'ID': request.form.get('id'), 'Password': password}
            cur.execute("UPDATE Users SET Password=:Password WHERE ID=:ID;", values)
            conn.commit()
            message = 'Регистрация прошла успешно'
            return render_template('register.html', message = message)
        else:
            message = 'Пользователь найден используйте пароль для входа'
            return render_template('register.html', message = message)
    else:
        message = 'Зарегистрироваться могу только участника клана HG'
        return render_template('register.html', message = message)

@app.route('/users',methods=['post','get'])
def users():
    rights = user_rights(request.cookies.get('Id'))
    right = False
    if rights != False:
        for le in rights:
            if ('Admin' in le) == True:
                right = True
                break
    if right == True:
        where = ' '
        users = get_info(where)
        x=1
        html = '<table class="table table-dark table-striped p-2 mb-2 mt-2"><thead>' \
               '<tr><th scope="col">#</th><th scope="col">ID</th><th scope="col">Имя в дискорде</th><th scope="col">Имя в игре</th><th scope="col">Управление</th>' \
               '</tr></thead><tbody>'
        for ln in users:
            html += '<tr><th scope="row">'+str(x)+'</th>' \
                    '<td>'+str(ln[0])+'</td>' \
                    '<td>'+str(ln[1])+'</td>' \
                    '<td>' + str(ln[4]) + '</td>' \
                    '<td width="10%"><form>' \
                                          '<button class="btn mb-1 mt-1 btn-warning">Права</button>' \
                    '<button class="btn mb-1 mt-1 btn-warning">Данные</button></form></td>'
            x=x+1
        html += '</tbody></table>'
        html = flask.Markup(html)
        return render_template('users.html', table=html)
    else:
        return redirect('/')

@app.route('/logs')
def logs():
    rights = user_rights(request.cookies.get('Id'))
    right = False
    if rights != False:
        for le in rights:
            len = 'Admin' in le
            if len == True:
                right = True
                break
    if right == True:
        logger = open('resources/logs.txt', 'r', encoding="ISO-8859-1").read()
        return render_template('logs.html', to_configs=logger)
    else:
        logger = 'У вас нет прав на просмотр этого раздела'
        return render_template('not_rights.html', to_configs=logger)

@app.route('/song',methods=['post','get'])
def song():
    rights = user_rights(request.cookies.get('Id'))
    right = False
    if rights != False:
        for le in rights:
            if ('Admin' in le) == True or ('Music_ALL' in le) == True:
                right = True
                break
    if right == True:
        for x in request.form.items():
            y=1
        if request.method == 'GET':
            name = request.args.getlist('Name')
            new_music = request.args.getlist('new_music')
            if not new_music:
                return music_filler(name)
            else:
                save_new_music(name[0], new_music[0])
                name=[]
                return music_filler(name)
        else:
            name = request.form.get('Name')
            music = request.files['music']
            x=0
            if name == 'Upload' and music:
                filename = music.filename.split('.')
                if filename[1] == 'mp3' or filename[1] == 'MP3':
                    for root, dirs, files in os.walk("music"):
                        for file in files:
                            if file == music.filename:
                                print ('Такая песня уже есть')
                                x=1
                if x == 0:
                    save = 'music/'+music.filename
                    print (save)
                    music.save(save)
            return music_filler(name)
    else:
        music_welcome = 'У вас нет прав на просмотр этого раздела'
        return render_template('not_rights.html', to_configs=music_welcome)

@app.route('/music/<path:filename>')
def download_file(filename):
    return send_from_directory('music/', filename)

@app.route('/exit',methods=['post','get'])
def exit():
    exit = request.form['exit']
    sql = "DELETE FROM Session where ID=" + str(exit)
    cur.execute(sql)
    res = flask.make_response(flask.redirect('/'))
    res.set_cookie('123', '1', max_age=0)
    res.set_cookie('Id', '1', max_age=0)
    res.set_cookie('Rights', '1', max_age=0)
    return res

def music_filler(name):
    music_wel = music()
    music_welcome = []
    if not name:
        name.append('Костыль')
    for mu in music_wel:
        if mu[1] != None and mu[0]!=name[0]:
            mu_tmp = '<audio src="music/' + mu[1] + '" controls></audio>'
            form = '<form method="GET" action="/song"> <button type="submit" name="Name" value="' + mu[0] + '">Изменить звук</button></form>'
            music_welcome.append([mu[0], mu_tmp,form])
        elif mu[0]!=name[0]:
            mu_tmp = 'Музыка не установлена'
            form = '<form method="GET" action="/song"> <button type="submit" name="Name" value="'+mu[0]+'">Изменить звук</button></form>'
            music_welcome.append([mu[0], mu_tmp,form])
        else:
            mu_tmp ='<form method="GET" action="/song"> <select name="new_music">'
            for root, dirs, files in os.walk("music"):
                for filename in files:
                    mu_tmp += '<option>'+filename+'</option>'
            mu_tmp += '</select>'
            form = '<button type="submit" name="Name" value="' + mu[0] + '">Сохранить звук</button></form>'
            music_welcome.append([mu[0], mu_tmp,form])
    return render_template('song.html', to_music=music_welcome)

def music():
    cur.execute("SELECT Name_discord,Song FROM Users;")
    music_welcome = cur.fetchall()
    return music_welcome

def save_new_music(Name, Music):
    values = {'Name': Name, 'Music': Music}
    cur.execute("UPDATE Users SET Song=:Music WHERE Name_discord=:Name;", values)
    conn.commit()

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

def check_session(id_user):
    if id_user:
        sql = "SELECT COUNT(*) FROM Session WHERE ID="+id_user
        cur.execute(sql)
        count = cur.fetchall()
        if int(count[0][0])>0:
            return True
        else:
            return False
    else:
        return False

def get_info(Where):
    if Where:
        sql = "SELECT * FROM Users"+Where
        cur.execute(sql)
        info = cur.fetchall()
        if info:
            return info
        else:
            return False
    else:
        return False

if __name__ == '__main__':
    app.run(port=80, host='0.0.0.0')