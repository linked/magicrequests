import requests
from requests import *
from requests.auth import HTTPProxyAuth

from lxml import etree

import urlparse
import random
import time
import collections

try:
	import gevent
except:
	gevent = False

EXCLUDED_LINK_EXTENSIONS = ('jpg', 'gif', 'jpeg','pdf', 'doc', 'docx', 'ppt', 'txt', 'png', 'zip', 'rar', 'mp3')

from requests.utils import default_user_agent

class UserAgent(object):
	useragents = ['Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.8.1.6) Gecko/20070725 Firefox/2.0.0.6', 
			'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)', 
			'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.04506.30)', 
			'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; .NET CLR 1.1.4322)',
			'Mozilla/5.0 (X11; Arch Linux i686; rv:2.0) Gecko/20110321 Firefox/4.0','Mozilla/5.0 (Windows; U; Windows NT 6.1; ru; rv:1.9.2.3) Gecko/20100401 Firefox/4.0 (.NET CLR 3.5.30729)', 
			'Mozilla/5.0 (Windows NT 6.1; rv:2.0) Gecko/20110319 Firefox/4.0','Mozilla/5.0 (Windows NT 6.1; rv:1.9) Gecko/20100101 Firefox/4.0',
			'Opera/9.20 (Windows NT 6.0; U; en)','Opera/9.00 (Windows NT 5.1; U; en)', 
			'Opera/9.64(Windows NT 5.1; U; en) Presto/2.1.1']
	random_user_agents = useragents
	def __str__(self):
		return random.choice(self.useragents)

	@classmethod
	def default(cls):
		cls.useragents = [default_user_agent()]

	@classmethod
	def not_default(cls):
		cls.useragents = cls.random_user_agents


requests.defaults.defaults['base_headers']['User-Agent'] = UserAgent()

class Session(requests.sessions.Session):
	def __init__(self, *args, **kwargs):
		super(Session, self).__init__(*args, **kwargs)
		if 'User-Agent' not in self.headers:
			self.headers['User-Agent'] = str(UserAgent())

requests.sessions.Session = Session


class Response(requests.Response):
	def __contains__(self, item):
		return item.lower() in self.text.lower()

	def xpath(self, xpath):
		if not hasattr(self, '_xpath'):
			try:
				self._xpath = etree.HTML('\n'.join(self.text.split('\n')[1:] if self.text.split('\n')[0].startswith('<?') else self.text.split('\n')))
			except:
				self._xpath = None
		if self._xpath is not None:
			return [urlparse.urljoin(self.url, result) if isinstance(result, basestring) and xpath.split('@')[-1] in ('href', 'src', 'action') and not result.startswith('http') else result for result in self._xpath.xpath(xpath)]
		else:
			return []

	@property
	def domain(self):
		if not hasattr(self, '_domain'):
			self._domain = urlparse.urlparse(self.url).netloc
		return self._domain	

	def links(self):
		try:
			return [unicode(link) for link in self.xpath('//a/@href') if (link.startswith('http') and '://' in link) or '://' not in link]
		except:
			return []

	def filter_links(self, links):
		return [link for link in links if not link.split('.')[-1].lower() in EXCLUDED_LINK_EXTENSIONS]

	def internal_links(self):
		try:
			return [link for link in self.links() if urlparse.urlparse(link).netloc == self.domain]
		except:
			pass

	def external_links(self):
		return [link for link in self.links() if link.startswith('http') and urlparse.urlparse(link).netloc != self.domain]

	def dofollow_links(self):
		return [unicode(link) for link in self.xpath('//a[@rel!="nofollow" or not(@rel)]/@href')]
	
	def nofollow_links(self):
		return [unicode(link) for link in self.xpath('//a[@rel="nofollow"]/@href')]

	def link_with_url(self, url, domain=False):
		if domain:
			url = urlparse.urlparse(url).netloc
		for link in self.links():
			if link == self.url:
				return link
			if link.rstrip('/') == self.url:
				return link.rstrip('/')
			if link+'/' == self.url:
				return link+'/'
		return False

	def save(self, handle):
		if isinstance(handle, basestring):
			handle = open(handle, 'w')
		handle.write(self.content)
		handle.close()

	def title(self):
		title = self.xpath('//title/text()')
		if len(title):
			return title[0].strip()
		else:
			return None

	def form(self, form='//form'):
		return Form(self, form=form)

	def biggest_form(self, **kwargs):
		forms = [Form(self, form) for form in self.xpath('//form')]
		if len(forms):
			form = sorted(forms, key=lambda form: len(form.data), reverse=True)[0]
			form.data.update(kwargs)
			return form


requests.models.Response = Response

class Form(object):
	def __init__(self, parent, form):
		self.data = {}
		self.types = {}
		self.parent = parent
		if isinstance(form, basestring):
			print parent.xpath(form)
			self.form = parent.xpath(form)[0]
		else:
			self.form = form
		
		for input_field in self.form.xpath('descendant::input'):
			self.types[input_field.get('name')] = input_field.get('type') or 'text'
			if input_field.get('type') == 'radio' and input_field.get('checked') == None:
				continue
			if input_field.get('name'):
				if input_field.get('name') in self.data and not input_field.get('value'):
					continue
				if input_field.get('type') == 'checkbox':
					if input_field.get('checked') != None:
						if input_field.get('name').endswith('[]'):
							if input_field.get('name') not in self.data:
								self.data[input_field.get('name')] = []
							self.data[input_field.get('name')].append(input_field.get('value') or 'on')
						else:
							self.data[input_field.get('name')] = input_field.get('value') or 'on'
				else:
					if input_field.get('name').endswith('[]'):
						if input_field.get('name') not in self.data:
							self.data[input_field.get('name')] = []
						self.data[input_field.get('name')].append(input_field.get('value') or '')
					else:
						self.data[input_field.get('name')] = input_field.get('value') or ''

		for select_field in self.form.xpath('descendant::select'):
			self.types[select_field.get('name')] = 'select'
			if select_field.get('name'):
				selected_option = select_field.xpath('descendant::option[@selected]')
				if len(selected_option):
					self.data[select_field.get('name')] = selected_option[0].get('value')
				else:
					options = select_field.xpath('descendant::option')
					if len(options):
						self.data[select_field.get('name')] = random.choice(options).get('value')

		for textarea in self.form.xpath('descendant::textarea'):
			self.types[textarea.get('name')] = 'textarea'
			self.data[textarea.get('name')] = textarea.get('value') or ''

		self.img_urls = []
		for img in self.form.xpath('descendant::img'):
			url = img.get('src')
			if url:
				self.img_urls.append(urlparse.urljoin(self.parent.url, url))

		self.action = self.form.get('action')
		if not self.action.startswith('http'):
			self.action = urlparse.urljoin(self.parent.url, self.action)

class ProxyManager(object):
	def __init__(self, proxy, min_delay=10, max_delay=10):
		if isinstance(proxy, basestring):
			if proxy.startswith('http'):
				proxy = requests.get(proxy).content
			self.records = [line.strip() for line in proxy.strip().split('\n')]
		elif isinstance(proxy, collections.Iterable):
			self.records = proxy
		records = []
		for record in self.records:
			if '@' not in record:
				ip, port, username, password = record.split(':')
				record = username+':'+password+'@'+ip+':'+port
			records.append('http://'+record+'/')
		self.records = dict(zip(records, [0] * len(self.records)))

		self.min_delay = min_delay
		self.max_delay = max_delay

	@property
	def proxy(self):
		while True:
			records = [record for record, record_time in self.records.items() if record_time + random.randint(self.min_delay, self.max_delay) < time.time()]
			if len(records):
				record = random.sample(self.records, 1)[0]
				self.records[record] = time.time()
				return {'http': record, 'https': record}
			else:
				if gevent:
					gevent.sleep(0.2)
				else:
					time.sleep(0.2)

	def copy(self):
		return ProxyManager(self.records.keys(), min_delay=self.min_delay, max_delay=self.max_delay)
		