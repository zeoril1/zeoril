from flask import Flask,render_template,send_from_directory
import sqlite3

app = Flask(__name__)
conn = sqlite3.connect('resources/discord.sqlite3', check_same_thread=False)
cur = conn.cursor()

@app.route('/')
def index():
    return render_template('index.html')

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

if __name__ == '__main__':
    app.run()
