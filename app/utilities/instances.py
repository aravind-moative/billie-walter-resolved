def get_db_manager():
    from app import app
    return app.state.db_manager


def get_admin_db_manager():
    from app import app
    return app.state.admin_db_manager


def get_tts():
    from app import app
    return app.state.tts
