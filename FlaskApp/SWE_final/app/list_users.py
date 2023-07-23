import firebase_admin
from firebase_admin import auth, credentials

cred = credentials.Certificate("firebase_key.json")
default_app = firebase_admin.initialize_app(cred)

def list_all_users():
    # Note: This is a naive implementation and won't work if you have more than 1000 users.
    # For larger user bases, you'll need to implement pagination. Check Firebase docs for more info.
    users = auth.list_users().iterate_all()
    for user in users:
        print('User ID: {0} Email: {1}'.format(user.uid, user.email))

list_all_users()