from sqlalchemy import select

from integration.orm.versions import Version

def get_versions():
    return select(Version)