import os
import re
import errno
import procfs
from configobj import ConfigObj, ConfigObjError
try:
	if (os.getuid() == 0):
		import dmidecode
		have_dmidecode = True
	else:
		have_dmidecode = False
except:
	have_dmidecode = False
try:
	import syspurpose.files
	have_syspurpose = True
except:
	have_syspurpose = False

import tuned.consts as consts
import tuned.logs
from tuned.utils.commands import commands

log = tuned.logs.get()

class ProfileRecommender:

	def __init__(self):
		self._commands = commands()

	def recommend(self, hardcoded = False):
		profile = consts.DEFAULT_PROFILE
		if hardcoded:
			return profile
		matching = self.process_config(consts.RECOMMEND_CONF_FILE)
		if matching is not None:
			return matching
		files = {}
		for directory in consts.RECOMMEND_DIRECTORIES:
			contents = []
			try:
				contents = os.listdir(directory)
			except OSError as e:
				if e.errno != errno.ENOENT:
					log.error("error accessing %s: %s" % (directory, e))
			for name in contents:
				path = os.path.join(directory, name)
				files[name] = path
		for name in sorted(files.keys()):
			path = files[name]
			matching = self.process_config(path)
			if matching is not None:
				return matching
		return profile

	def process_config(self, fname):
		matching_profile = None
		try:
			if not os.path.isfile(fname):
				return None
			config = ConfigObj(fname, list_values = False, interpolation = False)
			for section in list(config.keys()):
				match = True
				for option in list(config[section].keys()):
					value = config[section][option]
					if value == "":
						value = r"^$"
					if option == "virt":
						if not re.match(value,
								self._commands.execute("virt-what")[1], re.S):
							match = False
					elif option == "system":
						if not re.match(value,
								self._commands.read_file(
								consts.SYSTEM_RELEASE_FILE), re.S):
							match = False
					elif option[0] == "/":
						if not os.path.exists(option) or not re.match(value,
								self._commands.read_file(option), re.S):
							match = False
					elif option[0:7] == "process":
						ps = procfs.pidstats()
						ps.reload_threads()
						if len(ps.find_by_regex(re.compile(value))) == 0:
							match = False
					elif option == "chassis_type":
						if have_dmidecode:
							for chassis in dmidecode.chassis().values():
								chassis_type = chassis["data"]["Type"].decode(
										"ascii")
								if re.match(value, chassis_type, re.IGNORECASE):
									break
							else:
								match = False
						else:
							log.debug("Ignoring 'chassis_type' in '%s',\
								dmidecode is not available." % fname)
					elif option == "syspurpose_role":
						if have_syspurpose:
							s = syspurpose.files.SyspurposeStore(
									syspurpose.files.USER_SYSPURPOSE,
									raise_on_error = True)
							role = ""
							try:
								s.read_file()
								role = s.contents["role"]
							except (IOError, OSError, KeyError) as e:
								if hasattr(e, "errno") and e.errno != errno.ENOENT:
									log.error("Failed to load the syspurpose\
										file: %s" % e)
							if re.match(value, role, re.IGNORECASE) is None:
								match = False
						else:
							log.error("Failed to process 'syspurpose_role' in '%s'\
								, the syspurpose module is not available" % fname)

				if match:
					# remove the ",.*" suffix
					r = re.compile(r",[^,]*$")
					matching_profile = r.sub("", section)
					break
		except (IOError, OSError, ConfigObjError) as e:
			log.error("error processing '%s', %s" % (fname, e))
		return matching_profile
