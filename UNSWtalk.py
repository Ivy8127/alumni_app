#!/web/cs2041/bin/python3.6.3

# COMP2041 assignment 3. Spec:https://cgi.cse.unsw.edu.au/~cs2041/assignments/UNSWtalk/index.html
# This is a social media type platform written in flask.  This file uses a database that is created in an acompanying file called database_creator.py
# throughout the code, you will see the term 'pcr' many times. This stands for 'Posts, Comments and Replies'
# Friendships are saved bidirectionally in the database. See database_creator for more details on how friendship are handled in the supplied data

import smtplib
import os
import re
import pathlib
import sqlite3
import uuid
from flask import Flask, render_template, session, g, request, redirect, make_response, url_for, flash
from datetime import datetime
from flask import Markup
from werkzeug.utils import secure_filename

DATABASE = 'database.db'
app = Flask(__name__)

#used to import CSS files
def get_resource_as_string(name, charset='utf-8'):
    with app.open_resource(name) as f:
        return f.read().decode(charset)
app.jinja_env.globals['get_resource_as_string'] = get_resource_as_string

# defines num items per page for pagination
ITEMS_PER_PAGE = 16


# BEGIN DATABASE FUNCTIONS:
# referenced from http://flask-.readthedocs.io/en/0.2/patterns/sqlite3/ and # http://flask.pocoo.org/snippets/37/
def connect_db():
    return sqlite3.connect(DATABASE)

# initialises connection before requests
@app.before_request
def before_request():
    g.db = connect_db()

# query function
def query_db(query, args=(), one=False):
    cur = g.db.execute(query, args)
    rv = [dict((cur.description[idx][0], value)
               for idx, value in enumerate(row)) for row in cur.fetchall()]
    return (rv[0] if rv else None) if one else rv

# insert function. format fields are fields to update, values are the values to update to
# since some insert operations require a date, we have a boolean date parameter
# if there is a date, assumes date is the final field/value
def insert(table, date, fields=(), values=()):
    # g.db is the database connection
    cur = g.db.cursor()
    # if the field requires a date field
    # assumes date is the final value
    if date:
        query = 'INSERT INTO %s (%s) VALUES (%s)' % (
            table,
            ', '.join(fields),
            ', '.join(['?'] * (len(values)-1)) + ', DATETIME(?)',
        )
    else:
        query = 'INSERT INTO %s (%s) VALUES (%s)' % (
        table,
        ', '.join(fields),
        ', '.join(['?'] * len(values))
        )
    cur.execute(query, values)
    g.db.commit()
    id = cur.lastrowid
    cur.close()
    return id

# deletes items from table that match the conditions
def delete(table, conditions=()):
    # g.db is the database connection
    cur = g.db.cursor()
    query = 'DELETE FROM %s WHERE %s ' % (
        table,
        ' and '.join(conditions)
    )
    cur.execute(query)
    g.db.commit()
    cur.close()
    return id

# updates field values in table that match conditions
def update(table, fields=(), conditions=()):
    # g.db is the database connection
    cur = g.db.cursor()
    query = 'UPDATE %s SET %s where %s' % (
        table,
        ', '.join(fields),
        ' and '.join(conditions)
    )
    cur.execute(query)
    g.db.commit()
    cur.close()
    return id

# closes connection after requests
@app.after_request
def after_request(response):
    g.db.close()
    return response
# END DATABASE FUNCTIONS

# landing page on first arrival
@app.route('/', methods=['GET', 'POST'])
def landing():
    return render_template('start.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    # if loggin user in
    if request.method == 'POST':
        # extract fields
        z_id = request.form.get('z_id', '')
        password = request.form.get('password', '')
        user = query_db("select * from users where z_id=? and password=?",[z_id, password], one=True)
        # if user is found
        if user:
            
                session["current_user"] = z_id
                response = make_response(redirect(url_for("home")))
                return response
        
        else:
            flash("Unknown username or password")
            response = make_response(render_template('login.html'))
            return response
    # otherwise return template
    else:
        return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    # if we are registering new user
    if request.method == 'POST':
        # extract fields
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        z_id = request.form.get('z_id', '')
        name = request.form.get('name', '')
        existing_user = query_db("select * from users where z_id=?",[z_id], one=True)
        # if z_id already in use, return error
        if existing_user:
            flash("A user with this zid has already made an account")
            response = make_response(render_template('signup.html'))
            return response
        # otherwise, sign up
        
    else:
        return render_template('signup.html')

@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        # extract details
        z_id = request.form.get('z_id', '')
        user = query_db("select * from users where z_id=?", [z_id], one=True)
        # if we find a user
        if user:
            # send the reset email
            sendmail(user["email"], "Password Reset", passwordResetEmailText(z_id))
            flash("Password Reset sent")
        else:
            flash("Unknown user")
        return make_response(redirect(url_for("landing")))
    else:
        return make_response(render_template('forgot.html'))

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    if "current_user" in session:
        session.pop("current_user", None)
        response = make_response(redirect(url_for('landing')))
        return response
    else:
        response = make_response(redirect(url_for('landing')))
        return response


# handles the search feature. Searches based on user name/id and posts, comments and replie
@app.route('/search', methods=['GET', 'POST'])
@app.route('/search/<int:page>', methods=['GET', 'POST'])
def search(page=1):
    # redirect back to login if not authenticated
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))
    # extract query
    search_query = request.form.get('search_query', '')
    # find users whos name or z_id match
    matched_users = query_db("select * from users where z_id like ? or name like ? and verified=1", ['%'+search_query+'%', '%'+search_query+'%'])
    # find matching pcrs
    pcrs = getPCRThatMention(search_query)
    # sort them by date
    pcrs = sorted(pcrs, key=lambda k: datetime.strptime(k['created_at'], '%Y-%m-%d %H:%M:%S'), reverse=True)
    # sanitize them
    for i in pcrs: sanitizePCR(i)

    # pagination for this page is complicated, since we have two different lists (users and pcrs) being paginated on one page.
    # there is one page parameter, which will continue until the longer of the two lists runs out of elements.
    # if one of the lists runs out of elements before the longer one does, we simply stop displaying results for the shorter list

    # calculate pagination indicies
    users_start = (page-1)*ITEMS_PER_PAGE
    users_end = page*ITEMS_PER_PAGE
    pcrs_start = (page-1)*ITEMS_PER_PAGE
    pcrs_end = page*ITEMS_PER_PAGE
    # set next/ prev page count
    prev_page = page-1
    next_page = page+1
    # check if we are out of bounds. If so, fix
    if users_end >= len(matched_users):
        users_end = len(matched_users)
    if users_start < 0: users_start = 0
    if pcrs_end >= len(pcrs):
        pcrs_end = len(pcrs)
    if pcrs_start < 0: pcrs_start = 0

    #check if we have prev/next
    if users_end >= len(matched_users) and pcrs_end >= len(pcrs):
        next_page = None
    if users_start <= 0 and pcrs_end <= 0:
        prev_page = None

    # render template with appropraite list elements
    return render_template('search.html', matched_users=matched_users[users_start:users_end], pcrs=pcrs[pcrs_start:pcrs_end], prev_page=prev_page, next_page=next_page, search_query=search_query)

# handles a users profile
@app.route('/profile/<z_id>', methods=['GET', 'POST'])
def profile(z_id):
    # redirect back to login if not authenticated
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))

    # get the users details
    user_details = query_db("select * from users where z_id=?", [z_id], one=True)
    # get the posts, comments and replies.
    pcrs = query_db("select * from posts where user=? order by created_at DESC", [z_id])
    # sanitize them
    for i in pcrs: sanitizePCR(i)
    # get the users friend details
    friends = getFriends(z_id)
    # get the friendship status between current_user and this user (not used if a user is accessing his own page)
    friendship = query_db("select * from friends where reference=? and friend=?",[session["current_user"], z_id], one=True)
    # check if the current user has a pending friend request from this pages user (not used if a user is accessing his own page)
    pending_request = query_db("select * from friends where reference=? and friend=? and accepted=0",[z_id, session["current_user"]], one=True)
    return render_template('profile.html', profile_z_id=z_id ,user_details=user_details, public_attrs=["program", "zid", "birthday", "name", "bio"], pcrs=pcrs, friends=friends, friendship=friendship, pending_request=pending_request)


# gets a users friends information
def getFriends(z_id):
    friends = []
    # find the users friends from the friends table
    results = query_db("select friend from friends where reference=? and accepted=1", [z_id])
    # find info on each friend
    for result in results:
        friend_data = query_db(
            "select * from users where z_id=?", [result["friend"]], one=True)
        friends.append(friend_data)
    return friends

# cleans up a list of posts comments and replies by calling sub function
def sanitizePCR(object):
    sanitizeTime(object)
    replaceTagsWithLinks(object)
    sanitizeNewLines(object)

# replaces '\n' with html <br> element
def sanitizeNewLines(object):
    object["message"] = Markup(re.sub(r"\\n", "<br>", object["message"]))


# formats the time
def sanitizeTime(object):
    # remove time zone because cant get working with %z and convert to datetime
    time = datetime.strptime(object["created_at"], '%Y-%m-%d %H:%M:%S')
    # update to desired format
    object["created_at"] = datetime.strftime(time, ' %H:%M:%S, %a %d %m %Y')

# replaces all tags with links to the users profile
def replaceTagsWithLinks(object):
    text = object["message"]
    # find all instances of zXXXXXXX and replace with link
    for match in re.findall(r"\b(z\d{7})\b", text):
        url = url_for('profile', z_id=match)
        # find the name of the user who is tagged
        user = query_db("select * from users where z_id=?", [match], one=True)
        text = text.replace(match, "<a href='%s'>%s</a>" % (url, user["name"]))
    object["message"] = text

# loggined in users home page. Handles the feed
@app.route('/home', methods=['GET', 'POST'])
@app.route('/home/<int:page>', methods=['GET', 'POST'])
def home(page=1):
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))

    # the feed consists of three elements mixed together. we first call functions to get the data
    # we then call setObjectSource and setObjectType to help us with displaying them in one feed. see respective functions for explanation on usage
    friends_content = getFriendsPosts(session["current_user"])
    friends_content = setObjectSource(setObjectType(friends_content, "post"),"friend")
    mentions = getPCRThatMention(session["current_user"])
    mentions = setObjectSource(mentions, "mention")
    users_posts = query_db("select * from posts where user=? order by created_at DESC", [session["current_user"]])
    users_posts = setObjectSource(setObjectType(users_posts, "post"), "self")
    # group the elements into a single list
    feed = friends_content + users_posts + mentions
    # sort them by date
    feed = sorted(feed, key=lambda k: datetime.strptime(k['created_at'], '%Y-%m-%d %H:%M:%S'), reverse=True)
    # sanitize them
    for i in feed: sanitizePCR(i)
    # calculate pagination indicies
    start = (page-1)*ITEMS_PER_PAGE
    end = page*ITEMS_PER_PAGE
    # set next/ prev, possible to be changed on boundaries
    prev_page = page-1
    next_page = page+1
    # check if we are out of bounds
    if page <= 1: start = 0; prev_page = None;
    if end >= len(feed): end = len(feed); next_page = None;
    return render_template('home.html', feed=feed[start:end], prev_page=prev_page, next_page=next_page)

# gets posts of friends
def getFriendsPosts(z_id):
    query = """select * from posts where user in
    (select friend from friends where reference=?)
     order by created_at DESC"""
    friends_posts = query_db(query, [z_id])
    return friends_posts

# gets all posts comments and replies that mention the parameter
def getPCRThatMention(z_id):
    post_query = "select * from posts where message like ? order by created_at desc"
    comment_query = "select * from comments where message like ? order by created_at desc"
    reply_query = "select * from replies where message like ? order by created_at desc"
    # we then set the type field so we can tell whether an object is a post comment or reply later
    posts = setObjectType(query_db(post_query, ['%'+z_id+'%']), "post")
    comments = setObjectType(query_db(comment_query, ['%'+z_id+'%']), "comment")
    replies = setObjectType(query_db(reply_query, ['%'+z_id+'%']), "replies")
    return (posts + comments + replies)

# sets an identifier in the object to either post, comment or reply
def setObjectType(objects, type):
    for object in objects:
        object["type"] = type
    return objects

# sets source to either mention, friend or self to help with displaying custom messages on home feed
def setObjectSource(objects, type):
    for object in objects:
        object["source"] = type
    return objects

# handles creation of new posts
@app.route('/newpost', methods=['GET', 'POST'])
def newpost():
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))

    message = request.form.get('message', '')
    # if we are uploading media
    if "media" in request.files:
        file = request.files["media"]
        filename = secure_filename(file.filename)
        # make the name slightly unique in case multiple people upload image w same name
        filename = session["current_user"] + "-" + filename
        if file.filename != "":
            # save the file
            file.save(os.path.join("static/images", filename))
            # determine image vs video
            file_type = determineMediaType(filename)
            insert("posts", True, ["id", "user", "message", "media_type", "content_path", "created_at" ], [str(uuid.uuid4()).replace('-',''), session["current_user"], "", file_type, "images/%s" % filename, getCurrentDateTime()])
    else:
        # insert text message
        insert("posts", True, ["id", "user", "message", "media_type", "created_at"], [str(uuid.uuid4()).replace('-',''),session["current_user"], message,  "text", getCurrentDateTime()])
    return redirect(request.referrer)

# deletes posts
@app.route('/delete_post', methods=['GET', 'POST'])
def delete_post():
    # check user is logged
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))
    post_id = request.form.get('post_id', '')
    # perform delete
    deletePost(post_id)
    return redirect(url_for("home"))

# deletes a post with the id supplied, and all dependent comments and replies
def deletePost(post_id):
    # find all dependent comments and delete them
    comments = query_db("select * from comments where post=?", [post_id])
    for comment in comments:
        deleteComments(comment["id"])
    # then delete post
    delete("posts", ["id = '%s'" % post_id])

# creates new comments
@app.route('/newcomment', methods=['GET', 'POST'])
def newcomment():
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))

    message = request.form.get('message', '')
    post_id = request.form.get('post_id', '')
    # are we commenting media or a text
    if "media" in request.files:
        file = request.files["media"]
        filename = secure_filename(file.filename)
        # make the name slightly unique in case multiple people upload image w same name
        filename = session["current_user"] + "-" + filename
        if file.filename != "":
            # save file
            file.save(os.path.join("static/images", filename))
            # check video vs image
            file_type = determineMediaType(filename)
            insert("comments", True, ["id", "post", "user", "message", "media_type", "content_path", "created_at" ], [str(uuid.uuid4()).replace('-',''), post_id, session["current_user"], "", file_type, "images/%s" % filename, getCurrentDateTime()])
    else:
        # otherwise insert text comment
        insert("comments", True, ["id", "post", "user", "message", "media_type", "created_at"], [str(uuid.uuid4()).replace('-',''), post_id, session["current_user"], message,  "text", getCurrentDateTime()])
    return redirect(request.referrer)

# checks extension to determine image vs video
def determineMediaType(filename):
    extension = filename.rsplit('.', 1)[1]
    if extension in ["jpeg", "jpg", "png", "gif", "svg"]: return "image"
    elif extension in ["avi", "mov", "mp4", "flv", "webm"]: return "video"
    return None

# deletes comments
@app.route('/delete_comment', methods=['GET', 'POST'])
def delete_comment():
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))

    comment_id = request.form.get('comment_id', '')
    deleteComments(comment_id)
    return redirect(request.referrer)

# deletes a comment with the id supplied, and all dependent replies
def deleteComments(comment_id):
    # find all dependent replies and delete them
    replies = query_db("select * from replies where comment=?", [comment_id])
    for reply in replies:
        deleteReply(reply["id"])
    # then delete the comment
    delete("comments", ["id = '%s'" % comment_id])

# creates new replies
@app.route('/newreply', methods=['GET', 'POST'])
def newreply():
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))

    message = request.form.get('message', '')
    post_id = request.form.get('post_id', '')
    comment_id = request.form.get('post_id', '')
    # if we are posting media
    if "media" in request.files:
        file = request.files["media"]
        filename = secure_filename(file.filename)
        # make the name slightly unique in case multiple people upload image w same name
        filename = session["current_user"] + "-" + filename
        if file.filename != "":
            # save the file
            file.save(os.path.join("static/images", filename))
            # check video vs image
            file_type = determineMediaType(filename)
            insert("replies", True, ["id", "post","comment", "user", "message", "media_type", "content_path", "created_at" ], [str(uuid.uuid4()).replace('-',''), post_id, comment_id,session["current_user"], "", file_type, "images/%s" % filename, getCurrentDateTime()])
    else:
        # otherwise save text reply
        insert("replies", True, ["id", "comment", "post", "user", "message", "media_type", "created_at" ], [str(uuid.uuid4()).replace('-',''), comment_id, post_id, session["current_user"], message, "text" , getCurrentDateTime()])
    return redirect(request.referrer)

@app.route('/delete_reply', methods=['GET', 'POST'])
def delete_reply():
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))

    reply_id = request.form.get('reply_id', '')
    deleteReply(reply_id)
    return redirect(request.referrer)

# deletes a reply with the id supplied
def deleteReply(reply_id):
    delete("replies", ["id = '%s'" % reply_id])

# returns the current datetime in the database format
def getCurrentDateTime():
    d = datetime.now()
    return datetime.strftime(d, '%Y-%m-%d %H:%M:%S')

# displays a post with all its  comments and replies
@app.route('/post/<id>', methods=['GET', 'POST'])
def viewpost(id):
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))
    # query the post based on id
    post = query_db("select * from posts where id=? order by created_at DESC",[id], one=True)
    # get comments and replies
    pcr = getCommentsAndRepliesOfPost(post)
    return render_template('post.html', pcr=post)

# gets all the comments and replies of a post
def getCommentsAndRepliesOfPost(post):
    sanitizePCR(post)
    post["comments"] = []
    # itterate over comments
    for comment in query_db("select * from comments where post=?  order by created_at DESC", [post["id"]]):
        sanitizePCR(comment)
        # get the replies for each comment
        comment["replies"] = []
        for reply in query_db("select * from replies where comment=?  order by created_at DESC", [comment["id"]]):
            sanitizePCR(reply)
            # append to parent comment
            comment["replies"].append(reply)
        # append to return list
        post["comments"].append(comment)
    return post

@app.route('/removefriend', methods=['GET', 'POST'])
def removefriend():
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))
    # extract details
    friend_id = request.form.get('friend_id', '')
    # delete the friend from current users list and delete current user from friends list
    delete("friends", ["reference = '%s'" % session["current_user"], "friend = '%s'" % friend_id])
    delete("friends", ["friend = '%s'" % session["current_user"], "reference = '%s'" % friend_id])
    return redirect(request.referrer)

# sends a friend request
@app.route('/friend_request/<friend_id>', methods=['GET', 'POST'])
def friend_request(friend_id):
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))

    # find friends email
    friends_email = query_db("select * from users where z_id=?", [friend_id], one=True)["email"]
    # send email to friend
    sendmail(friends_email, "Friend Request", friendRequestEmailText(session["current_user"], friend_id))
    # add pending friend request
    insert("friends", False, ["reference", "friend", "accepted"], [session["current_user"], friend_id, 0])
    flash("Friend request sent")
    return redirect(request.referrer)

# accepts a friend request
@app.route('/addfriend/<reference>/<friend>', methods=['GET', 'POST'])
def addfriend(reference,friend):
    #update the pending friend request to be accepted
    update("friends", ["accepted=1"], ["reference='%s'" % reference, "friend='%s'" % friend])
    # create the bi directional friendship
    insert("friends", False, ["reference", "friend", "accepted"], [friend, reference, 1])
    flash("friend request accepted")
    return possibleBackRoute()


# checks if it is possible to go back to a previous page, othweise returns route to landing
# used when coming to site from email redirect
def possibleBackRoute():
    if request.referrer:
        return redirect(request.referrer)
    else:
        return redirect(url_for('landing'))

# resets password
@app.route('/reset/<z_id>', methods=['GET', 'POST'])
def reset(z_id):
    # if we are performing the pssword reset
    if request.method == 'POST':
        #get the new password and z_id
        password = request.form.get('password', '')
        z_id = request.form.get('z_id', '')
        # update password
        update("users", ["password='%s'"% password], ["z_id='%s'" % z_id])
        # log them in and go home
        session["current_user"] = z_id
        flash("Password successfully reset")
        return redirect(url_for("home"))
    # otherwise return form
    else:
        return render_template('reset.html', z_id=z_id)



# generates password reset email text
def passwordResetEmailText(z_id):
    return """
Hi %s,
Click the link below to reset your email:
%s
    """ % (z_id, url_for('reset', z_id=z_id, _external=True))

# generates friend request email text
def friendRequestEmailText(reference, friend_z_id):
    return """
Hi %s,
%s wants to add you as a friend. Click the link below to accept:
%s
    """ % (friend_z_id, reference, url_for('addfriend', reference=reference, friend=friend_z_id, _external=True))

# https://stackoverflow.com/a/26191922/4803964
# sends email via gmail stmp
def sendmail(to, subject, message):
    # set account details. shhh dont share ;)
    gmail_user = 'z5019999ass2'
    gmail_pwd = 'z5019999password'
    smtpserver = smtplib.SMTP("smtp.gmail.com",587)
    smtpserver.ehlo()
    smtpserver.starttls()
    smtpserver.ehlo()
    smtpserver.login(gmail_user, gmail_pwd)
    # set contents
    header = 'To:' + to + '\n' + 'From: ' + gmail_user + '\n' + 'Subject: ' + subject +  '\n'
    msg = header + '\n' + message + '\n\n'
    # send
    smtpserver.sendmail(gmail_user, to, msg)
    smtpserver.quit()

# deletes either a users profile pic or background image, depending on the image param
@app.route('/delete_user_image/<z_id>/<image>', methods=['GET', 'POST'])
def delete_user_image(z_id, image):
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))
    if image == "background":
        update("users", ["%s_path=''" % image], ["z_id='%s'" % z_id])
        flash("Background picture deleted")
    else:
        update("users", ["%s_path='images/defaultprofile.png'" % image], ["z_id='%s'" % z_id])
        flash("Profile picture deleted")
    return redirect(request.referrer)

# edits a users profile
@app.route('/edit_profile/<z_id>', methods=['GET', 'POST'])
def edit_profile(z_id):
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))
    # check if the user owns this page
    if session["current_user"] != z_id:
        flash("You cannot edit someone else's profile")
        return redirect(url_for("home"))

    if request.method == 'POST':
        # if there is a file, save it
        for field in ["image_path", "background_path"]:
            if request.files[field]:
                file = request.files[field]
                filename = secure_filename(file.filename)
                file.save(os.path.join("static/images", filename))
                # save in the user model
                update("users", ["%s='%s'" % (field, os.path.join("images", filename))], ["z_id='%s'" % z_id])

        # check which are not empty and update them to the new values
        fields = ["name","email","program","birthday","suburb","latitude","longitude", "bio"]
        fields_to_update = []
        for field in fields:
            if request.form.get(field):
                fields_to_update.append("%s='%s'" % (field, request.form.get(field)))
        update("users", fields_to_update, ["z_id='%s'" % z_id])
        flash("Details successfully saved")
        return redirect(request.referrer)
    else:
        # get the users info to prefill the form values
        user = query_db("select * from users where z_id=?", [z_id], one=True)
        # get courses to handle course management
        courses = query_db("select * from courses where user=?", [z_id])
        return render_template('edit_profile.html', z_id=z_id, user=user, courses=courses)

# handles friend recommendations
@app.route('/recommendations', methods=['GET'])
@app.route('/recommendations/<int:page>', methods=['GET'])
def recommendations(page=1):
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))
    else:
        # run matching query:
        # orders users by number of courses they take with current user (and checks they arent already friends/friend request pending)
        users = query_db("""
                 SELECT c2.user FROM courses c1
                INNER JOIN courses  c2 ON
                c1.code = c2.code and
                c1.year = c2.year and
                c1.semester = c2.semester where
                c1.user <> c2.user and
                c1.user=? and not exists (
                	select * from friends  where
                	(reference= c1.user and friend=c2.user) or (friend= c1.user and reference=c2.user)
                )
                GROUP BY c2.user  ORDER BY count(c2.user) DESC
                 """, [session["current_user"]])
        # get the user info for each
        recommendations = []
        for user in users:
            user_data = query_db(
                "select * from users where z_id=?", [user["user"]], one=True)
            recommendations.append(user_data)
        # calculate pagination indicies
        start = (page-1)*ITEMS_PER_PAGE
        end = page*ITEMS_PER_PAGE
        # set next/ prev, possible to be changed on boundaries
        prev_page = page-1
        next_page = page+1
        # check if we are out of bounds
        if page <= 1: start = 0; prev_page = None;
        if end >= len(recommendations): end = len(recommendations); next_page = None;
        return render_template("recommendations.html", recommendations=recommendations[start:end], prev_page=prev_page, next_page=next_page)

# removes a course from a users profile
@app.route('/remove_course/<course>', methods=['POST', 'GET'])
def remove_course(course):
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))
    # delete course
    delete("courses", ["user='%s'" % session["current_user"], "code='%s'" % course])
    return redirect(request.referrer)

# adds a course to a users profile
@app.route('/add_course', methods=['POST', 'GET'])
def add_course():
    # check user is logged in
    if not "current_user" in session:
        flash("You must be logged in to access that page")
        return redirect(url_for("login"))
    # extract info
    semester = request.form.get('semester', '')
    year = request.form.get('year', '')
    code = request.form.get('code', '').upper()
    # if the user is not already enrolled in the course
    if not query_db("select * from courses where user=? and year=? and code=? and semester=?", [session["current_user"], year, code, semester]):
        # enroll them
        insert("courses", False, ["user", "year", "code", "semester"], [session["current_user"], year, code, semester])
    return redirect(request.referrer)

if __name__ == '__main__':
    app.secret_key = os.urandom(12)
    app.run(threaded=True)
