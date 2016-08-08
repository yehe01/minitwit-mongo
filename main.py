import os
import time
from datetime import datetime
from hashlib import md5

from bson import ObjectId
from flask import Flask, request, session, g, redirect, url_for, abort, \
    render_template, flash
from flask_pymongo import PyMongo
from werkzeug.security import check_password_hash, generate_password_hash

from forms import LoginForm

MONGO_URL = os.environ.get('MONGODB_URI')
if not MONGO_URL:
    MONGO_URL = "mongodb://localhost:27017/test_flask_db";

app = Flask(__name__)
app.config.from_object(__name__)

app.config['MONGO_URI'] = MONGO_URL
mongo = PyMongo(app)

app.config.update(dict(
    DATABASE=os.path.join(app.root_path, 'flaskr.db'),
    SECRET_KEY='development key',
    USERNAME='admin',
    PASSWORD='default'
))
app.config.from_envvar('FLASKR_SETTINGS', silent=True)
PER_PAGE = 30
DEBUG = True
# WTF_CSRF_ENABLED = True
SECRET_KEY = 'you-will-never-guess'


@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        g.user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})


@app.route('/')
def timeline():
    """Shows a users timeline or if no user is logged in it will
    redirect to the public timeline.  This timeline shows the user's
    tweets as well as all the tweets of followed users.
    """
    if not g.user:
        return redirect(url_for('public_timeline'))

    users = mongo.db.users.find({"$or": [{'followed_by': g.user['_id']},
                                         {'_id': g.user['_id']}]})
    messages = compose_message(users)

    return render_template('timeline.html', messages=messages)


@app.route('/public')
def public_timeline():
    """Displays the latest tweets of all users."""
    users = mongo.db.users.find()
    messages = compose_message(users)

    return render_template('timeline.html', messages=messages)


@app.route('/<username>')
def user_timeline(username):
    """Display's a users tweets."""
    profile_user = get_user_by_name(username)
    if profile_user is None:
        abort(404)
    followed = False

    if g.user:
        followed_by = profile_user.get('followed_by', [])
        r = [user_id for user_id in followed_by if user_id == g.user['_id']]
        if len(r) > 0:
            followed = True

    users = mongo.db.users.find({'_id': profile_user['_id']})
    messages = compose_message(users)

    return render_template('timeline.html', messages=messages, followed=followed,
                           profile_user=profile_user)


@app.route('/<username>/follow')
def follow_user(username):
    """Adds the current user as follower of the given user."""
    if not g.user:
        abort(401)
    followed_user = get_user_by_name(username)
    if followed_user is None:
        abort(404)

    mongo.db.users.update({'_id': followed_user['_id']}, {"$push": {'followed_by': g.user['_id']}})
    flash('You are now following "%s"' % username)
    return redirect(url_for('user_timeline', username=username))


@app.route('/<username>/unfollow')
def unfollow_user(username):
    """Removes the current user as follower of the given user."""
    if not g.user:
        abort(401)
    followed_user = get_user_by_name(username)
    if followed_user is None:
        abort(404)

    mongo.db.users.update({'_id': followed_user['_id']}, {"$pull": {'followed_by': g.user['_id']}})
    flash('You are no longer following "%s"' % username)
    return redirect(url_for('user_timeline', username=username))


@app.route('/add_tweet', methods=['POST'])
def add_tweet():
    """Registers a new tweets for the user."""
    if not g.user:
        abort(401)
    if request.form['text']:
        mongo.db.users.update({'_id': g.user['_id']},
                              {"$push": {'tweets':
                                             {'text': request.form['text'], 'pub_date': int(time.time())}}})
        flash('Your tweet was recorded')
    else:
        flash('Content is empty.')

    return redirect(url_for('timeline'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        return redirect(url_for('timeline'))
    error = None

    form = LoginForm()
    if form.validate_on_submit():
        user = get_user_by_name(form.username.data)
        if user is None:
            error = 'Invalid username'
        elif not check_password_hash(user['pw_hash'],
                                     form.password.data):
            error = 'Invalid password'
        else:
            flash('You were logged in')
            session['user_id'] = str(user['_id'])
            return redirect(url_for('timeline'))
    return render_template('login.html', error=error, form=form)


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You were logged out')
    return redirect(url_for('public_timeline'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if g.user:
        return redirect(url_for('timeline'))
    error = None
    if request.method == 'POST':
        if not request.form['username']:
            error = 'You have to enter a username'
        elif not request.form['email'] or \
                        '@' not in request.form['email']:
            error = 'You have to enter a valid email address'
        elif not request.form['password']:
            error = 'You have to enter a password'
        elif request.form['password'] != request.form['password2']:
            error = 'The two passwords do not match'
        elif get_user_by_name(request.form['username']) is not None:
            error = 'The username is already taken'
        else:
            pw_hash = generate_password_hash(request.form['password'])
            username = request.form['username']
            email = request.form['email']
            mongo.db.users.insert({'username': username, 'email': email, 'pw_hash': pw_hash})
            flash('You were successfully registered and can login now')
            return redirect(url_for('login'))
    return render_template('register.html', error=error)


def format_datetime(timestamp):
    """Format a timestamp for display."""
    return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d @ %H:%M')


def get_user_by_name(username):
    return mongo.db.users.find_one({'username': username})


def gravatar_url(email, size=80):
    """Return the gravatar image for the given email address."""
    return 'http://www.gravatar.com/avatar/%s?d=identicon&s=%d' % \
           (md5(email.strip().lower().encode('utf-8')).hexdigest(), size)


# todo: sort tweets by date
def compose_message(users):
    messages = []
    for user in users:
        tweets = user.get('tweets', [])
        for tweet in tweets:
            message = {'username': user['username'], 'email': user['email'],
                       'pub_date': tweet['pub_date'], 'text': tweet['text']}
            messages.append(message)

    messages.sort(key=lambda x: x['pub_date'], reverse=True)
    return messages


app.jinja_env.filters['datetimeformat'] = format_datetime
app.jinja_env.filters['gravatar'] = gravatar_url


@app.route('/hello')
def hello():
    return 'Hello, World'


if __name__ == '__main__':
    app.run()
