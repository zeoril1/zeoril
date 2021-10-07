from flask import Flask,render_template

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/logs')
def logs():
    logger = open('resources/logs.txt', 'r', encoding="ISO-8859-1").read()
    return render_template('logs.html', to_configs=logger)

if __name__ == '__main__':
    app.run()