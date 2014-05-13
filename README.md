Sublime Text - WebDavSync
===========================

This is a small Sublime Text plugin for syncing your sublime project directory with a directory on a WebDAV server. That could be useful for WebDAV-based hotdeploy environments.

Installation
============

**Manually:**

Copy the content of this repository into a folder called ```WebDavSync``` in your Sublime Text packages directory.
(Open the menu */Preferences/Browse Packages* to determine the location of your packages directory)

**Via Package Control:**

Find *WebDavSync* in the Package Control installer and install it.


Setup
=====
Create a ```*.sublime-project``` file (see http://www.sublimetext.com/docs/2/projects.html for further consultation) and add a ```webdavsync``` section to the settings.

```JSON
{
    "folders":
    [
        {
            "path": "/path/to/your/project/root",
            "folder_exclude_patterns": []
        }
    ],
    "settings":
    {
        "webdavsync":
        {
            "host":"yourwebdavhost.com",
            "protocol":"https",
            "path":"/path/to/your/webdav/root",
            "username":"yourusername",
            "password":"yourpassword"
        }
    },
    "build_systems":
    [
    ]
}  
```

Open this file with Sublime Text (*Project/Open Project*) and from now on all files in your local root director(ies) are automatically uploaded to ```yourwebdavhost.com/path/to/your/webdav/root``` each time you save it there. If folders do not exist on the server, they will be created, before the file is uploaded there.

**For example:**

1. The local root path is ```/projectdir``` - see ```folders``` section in your ```*.sublime-project``` file

2. The local file ```/projectdir/static/js/app.js``` is saved

3. The remote root path is ```/version1```

The resulting webdav resource path is ```https://yourwebdavhost.com/version1/static/js/app.js``` and the remote path ```/version1/static/js``` will be created if necessary.


Features
========

1. Basic and Digest authentication
2. Uploading files and creating folders

Not Implemented
===============

1. Digest auth-int
2. Deleting folders and files



