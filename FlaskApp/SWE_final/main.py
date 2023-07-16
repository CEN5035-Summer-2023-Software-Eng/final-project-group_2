from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import pyrebase

config = {

}

firebase = pyrebase.initialize_app(config)
auth = firebase.auth()

app = Flask(__name__)
app.secret_key = 'secret'  # replace with your own secret key



@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            user = auth.sign_in_with_email_and_password(email, password)
            token = user['idToken']
            print(token)
            session['user'] = email
            session['token'] = token
            return jsonify({'status': 'success', 'username': email, 'token': token})
        except:
            return jsonify({'status': 'failure', 'message': 'Invalid credentials'}), 401
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            auth.create_user_with_email_and_password(email, password)
            return redirect(url_for('login'))
        except Exception as e:
            error_message = "Invalid Email or Password, Please try again."
            return render_template('register.html', error=error_message)
    return render_template('register.html')

@app.route('/welcome/<username>+<token>')
def welcome(username, token):
    print(token)
    print(session['user'])

    #print(session)
    if(token == session['token'] and username == session['user']):
        print("Correct Token")
        return render_template('welcome.html', username=username.split('@')[0])
    else:
        return render_template('login.html')
    

@app.route('/home')
def home():
    return "Welcome to home page!"

if __name__ == '__main__':
    app.run(debug=True)