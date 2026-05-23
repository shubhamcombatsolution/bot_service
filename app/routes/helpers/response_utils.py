from flask import jsonify

def success_response(message="Success", data=None, code=200):
    return jsonify({
        "status": True,
        "message": message,
        "data": data
    }), code


def error_response(message="Something went wrong", data=None, code=400):
    return jsonify({
        "status": False,
        "message": message,
        "data": data
    }), code