import sys

if sys.version_info[0] > 2:
	from queue import Queue
	from .webdav import WebDAV
else:
	from Queue import Queue
	from webdav import WebDAV

from threading import Thread
from threading import RLock

import sublime
import sublime_plugin


work_count_lock = RLock()
work_count = 0

# this is a map of all running webdav clients identified by user@host/path
# (in case there are parallel sublime text projects open)
WebDavSyncWebDavs = {}

# this method takes a dict containing a "davkey" (user@host/path) and creates a new client
# if there is nothing in the WebDavSyncWebDavs map for this davkey
def create_webdav_client(item):
	global WebDavSyncWebDavs
	if not "davkey" in item:
		return

	if not item["davkey"] in WebDavSyncWebDavs:
		WebDavSyncWebDavs[item["davkey"]] = WebDAV(protocol=item["protocol"], 
			host=item["host"], username=item["username"], password=item["password"])


WebDavSyncQueue = Queue()

def WebDavSyncWorker():

	global WebDavSyncQueue
	global WebDavSyncWebDavs
	global work_count_lock
	global work_count

	while True:
		if WebDavSyncQueue != None:
			item = WebDavSyncQueue.get()

			try:
				source_path = item["source_path"]

				source_folder = None

				for folder in item["folders"]:
					if folder in source_path:
						source_folder = folder
						break

				if source_folder != None:

					target_path = item["path"] + source_path[len(source_folder):]

					target_url = "{0}://{1}{2}".format(item["protocol"], item["host"], target_path).replace("\\","/")

					d = WebDavSyncWebDavs[item["davkey"]]

					try:
						if d != None:

							# mkdirs
							test_url = target_url[:target_url.rfind("/")]
							folders_to_create = []
							retryCount = 0
							while retryCount < 10:
								retryCount = retryCount + 1
								body = '<?xml version="1.0" encoding="utf-8" ?>' + \
								'<D:propfind xmlns:D="DAV:">' + \
								'<D:prop xmlns:R="%s">' % test_url + \
								'</D:prop>' + \
								'</D:propfind>'

								result = d.propfind(test_url,depth=0, body=body)
								result.read()
								if result.status == 207:
									break
								elif result.status == 404:
									retryCount = 0
									folders_to_create.append(test_url[test_url.rfind("/"):])
									test_url = test_url[:test_url.rfind("/")]

							for folder in reversed(folders_to_create):
								test_url = test_url + folder
								retryCount = 0
								while retryCount < 10:							
									retryCount = retryCount + 1
									result = d.mkcol(test_url)
									result.read()
									if result.status == 201:
										break

							f = open(source_path)
							content = f.read()

							response = d.put(target_url,content)
							d.close()								
					except Exception, e:
						print e
					finally:
						d.close()

			except Exception, e:
				print e
			finally:
				# this task is ready		
				WebDavSyncQueue.task_done()
				with work_count_lock:
					work_count = work_count - 1


# this is the background deamon
WebDavSyncDaemon = Thread(target=WebDavSyncWorker)
WebDavSyncDaemon.daemon = True
WebDavSyncDaemon.start()

class WebDavSync(sublime_plugin.EventListener):

	def update_status(self, view, i=0, dir=1):

		global work_count
		if work_count > 0:
			before = i % 8
			after = (7) - before
			if not after:
				dir = -1
			if not before:
				dir = 1
			i += dir			
			view.set_status('WebDavSync','WebDavSync [%s..%s]' % (' ' * before, ' ' * after))
			sublime.set_timeout(lambda: self.update_status(view,i,dir), 200)
		else:
			view.set_status("WebDavSync","WebDavSync finished successfully")

	def on_post_save(self, view):
		global WebDavSyncQueue
		global work_count_lock
		global work_count

		# check if there are webdav settings in the view (sublime-project file) - if not - return
		if not view.settings().has("webdavsync"):
			return

		settings = view.settings().get("webdavsync")
		if not ("host" in settings and "protocol" in settings and 
			"username" in settings and "password" in settings and
			"path" in settings):
				return
				
		source_path = view.file_name()
		item = {}
		item["host"] = settings.get("host")
		item["protocol"] = settings.get("protocol")
		item["username"] = settings.get("username")
		item["password"] = settings.get("password")
		item["path"] = settings.get("path")
		item["source_path"] = source_path
		item["folders"] = view.window().folders()

		# get the dav object
		item["davkey"] = "{0}@{1}{2}".format(item["username"],item["host"],item["path"])

		create_webdav_client(item)

		if WebDavSyncQueue != None:
			with work_count_lock:
				work_count = work_count + 1
			WebDavSyncQueue.put(item,False)
			self.update_status(view)