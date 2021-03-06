# -*- coding: utf-8 -*-
###########
# imports #
###########
# import json
from flask import Flask, request, make_response, abort, jsonify, g
from flask.ext.httpauth import HTTPBasicAuth
from pymongo import MongoClient
from gridfs import GridFS


################
# setup/config #
################

# set up Flask app and mongodb objects
app = Flask(__name__)
db = MongoClient().gfs_filestore
gfs = GridFS(db)
auth = HTTPBasicAuth()

# gfs_filestore.configs collection is assume to have one document 'max_file_size'
# with the maximum upload file size limit set by admin
# if document is not configured properly, default max size to 50MB
MAX_FILE_SIZE = db.configs.find_one({"name":"max_file_size"})['max_file_size'] if db.configs.find_one({"name":"max_file_size"}) else 50000000

#############################
# HTTPBasicAuthHelperMethod #
#############################

@auth.verify_password
def verify_password(username, password):
    # as this is the most secure fileserver in the world, we will just retrieve the
    # username and password information from db, if exists, and verify user; yayy!
    record = db.users.find_one({"username":username})
    if record is not None and record['username'] == username and record['password'] == password:
        g.username = username
        g.admin = record['admin'] or False
        return True
    else:
        return False

##########
# routes #
##########
@app.route('/configs', methods=['POST'])
@auth.login_required
def set_max():
    if g.admin:
        db.configs.update({"name":"max_file_size"},{'$set':{'max_file_size':request.args.get('max_file_size')}})
        return jsonify({'status': 'New maximum file size limit set'}),200
    else:
        return jsonify({'status':'You are not authorized to set configs.'}), 403

# register new user
# NOTE: not hashing or securing password to develop contrived app for demo/test purposes
@app.route('/users', methods=['POST'])
def new_user():
    username = request.args.get('username')
    password = request.args.get('password')
    if username is None or password is None:
        return jsonify({'status': 'Username and Password information not passed for new user.'}), 400 # missing arguments
    if db.users.find({"username":username}).count() > 0:
        return jsonify({'status': 'Existing user. Please select other username.'}), 400 # existing user
    new_user = db.users.insert({'username':username, 'password':password, 'admin':False})
    if db.users.find_one(new_user) is not None:
        return jsonify({'status':'New user created successfully'}), 201
    else:
        return jsonify({'status': 'Error ocurred during user creation'}), 500


# upload route expecting a filename in route and file contents in data
@app.route('/upload/<file_name>', methods=['POST'])
@auth.login_required
def upload(file_name):
    uploaded_file = request.data
    if len(uploaded_file) < MAX_FILE_SIZE:
        user_record = db.users.find_one({"username":g.username})
        with gfs.new_file(filename=file_name) as fp:
            file_id = fp.write(uploaded_file)
            if gfs.find_one(file_id) is not None:
                db.users.update({'username':g.username}, {'$set': {file_name:fp._id}}) # store different file types with the same name
                return jsonify({'status': 'File saved successfully'}), 200
            else:
                return jsonify({'status': 'Error occured while saving file'}), 500
    else:
        return jsonify({'status': 'File exceeded allowed size limit'}), 400

# download route returns contents for given filename if exists in gfs
@app.route('/download/<file_name>')
@auth.login_required
def download(file_name):
    try:
        user_record = db.users.find_one({'username':g.username})
        if "." in file_name:
            filename, extension = file_name.split('.')[0], file_name.split('.')[1]
            gfs_file = gfs.find_one({'_id': user_record[filename][extension]})
        else:
            gfs_file = gfs.find_one({'_id':user_record[file_name]})
        response = make_response(gfs_file.read())
        response.headers['Content-Type'] = 'application/octet-stream'
        response.headers["Content-Disposition"] = "attachment; filename={}".format(file_name)
        return response
    except:
        return jsonify({'status': 'File does not exist or you are not authorized to access this file.'}), 403

########
# main #
########
if __name__ == '__main__':
    # create admin user and prompt credentials to console
    if db.users.find_one({'username':'admin'}) is None:
        db.users.insert({'username':'admin', 'password':'admin','admin':True})
    print "* Administrator Username: 'admin' Password: 'admin'"
    if db.configs.find_one({'name':'max_file_size'}) is None:
        db.configs.insert({'name':'max_file_size', 'max_file_size':MAX_FILE_SIZE})
    app.run(debug=True)
