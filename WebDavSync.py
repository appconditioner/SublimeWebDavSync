import sublime
import sublime_plugin
import threading
import subprocess
import sys
import io
#import davlib
import webdav

if sys.version_info[0] > 2:
	from queue import Queue
else:
	from Queue import Queue

work_count_lock = threading.RLock()
work_count = 0

WebDavSyncWebDavs = {}

def create_webdav_client(item):
	d = WebDavSyncWebDavs[item["davkey"]] if item["davkey"] in WebDavSyncWebDavs else None
	if d == None:
		d = webdav.WebDAV(protocol=item["protocol"], host=item["host"], username=item["username"], password=item["password"])
		WebDavSyncWebDavs[item["davkey"]] = d


WebDavSyncQueue = Queue()

def WebDavSyncWorker():
	while True:
		if WebDavSyncQueue != None:
			item = WebDavSyncQueue.get()

			source_path = item["source_path"]

			source_folder = None

			for folder in item["folders"]:
				if folder in source_path:
					source_folder = folder
					break

			if source_folder != None:

				target_path = item["path"] + source_path[len(source_folder):]

				target_url = "{0}://{1}{2}".format(item["protocol"], item["host"], target_path)

				d = WebDavSyncWebDavs[item["davkey"]]

				if d != None:

					uploadReady = False
					# mkdirs
					test_url = target_url[:target_url.rfind("/")]
					print "target_folder: " + test_url
					folders_to_create = []
					retryCount = 0
					while retryCount < 10:
						retryCount = retryCount + 1
						result = d.propfind(test_url,depth=0)
						result.read()
						if result.status == 207:
							break
						elif result.status == 404:
							retryCount = 0
							folders_to_create.append(test_url[test_url.rfind("/"):])
							test_url = test_url[:test_url.rfind("/")]
							print test_url

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
					#print "Upload " + str(response.status) + ": " + source_path
					d.close()								

			# this task is ready		
			WebDavSyncQueue.task_done()
			global work_count_lock
			global work_count
			with work_count_lock:
				work_count = work_count - 1


WebDavSyncDaemon = threading.Thread(target=WebDavSyncWorker)
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
			global work_count_lock
			global work_count
			with work_count_lock:
				work_count = work_count + 1
			WebDavSyncQueue.put(item,False)
			self.update_status(view)