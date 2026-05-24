#!/usr/bin/env python3
import os

def fix_ownership(path):
    uid = os.environ.get("SUDO_UID")
    gid = os.environ.get("SUDO_GID")
    
    if uid and gid:
        os.chown(path, int(uid), int(gid))
