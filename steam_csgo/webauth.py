from steam import webauth


class WebAuth(webauth.WebAuth):
    def __init__(self):
        self.session = webauth.make_requests_session()

    @staticmethod
    def get_rsa(username):
        return WebAuth().get_rsa_key(username)

    def get_captcha(self, gid):
        return "https://steamcommunity.com/login/rendercaptcha/?gid=%s" % gid

    def get_(self, url, **kwars):
        for domain in ['store.steampowered.com', 'help.steampowered.com', 'steamcommunity.com']:
            self.session.cookies.set('Steam_Language', "english", domain=domain)
            self.session.cookies.set('birthtime', '-3333', domain=domain)
            self.session.cookies.set('sessionid', self.session_id, domain=domain)
        return self.session.get(url, **kwars)

    def _send_raw(self, username='', password='', timestamp='', captcha='',
                    captcha_gid=-1, email_code='', steam_id='', twofactor_code=''):
        data = {
            'username': username,
            "password": password,
            "emailauth": email_code,
            "emailsteamid": str(steam_id) if email_code else '',
            "twofactorcode": twofactor_code,
            "captchagid": captcha_gid,
            "captcha_text": captcha,
            "loginfriendlyname": "python-steam webauth",
            "rsatimestamp": timestamp,
            "remember_login": 'true',
            "donotcache": int(webauth.time() * 100000),
        }
        try:
            return self.session.post('https://steamcommunity.com/login/dologin/', data=data, timeout=15).json()
        except webauth.requests.exceptions.RequestException as e:
            raise webauth.HTTPError(str(e))

    def login_raw(self, username='', password='', timestamp='', captcha='', captcha_gid=-1,
              email_code='', steam_id='', twofactor_code='', language='english'):
        resp = self._send_raw(username=username, password=password, timestamp=timestamp,
                              captcha=captcha, captcha_gid=captcha_gid, email_code=email_code,
                              steam_id=steam_id, twofactor_code=twofactor_code)
        if resp['success'] and resp['login_complete']:
            self.logged_on = True

            for cookie in list(self.session.cookies):
                for domain in ['store.steampowered.com', 'help.steampowered.com', 'steamcommunity.com']:
                    self.session.cookies.set(cookie.name, cookie.value, domain=domain, secure=cookie.secure)

            self.session_id = webauth.generate_session_id()

            for domain in ['store.steampowered.com', 'help.steampowered.com', 'steamcommunity.com']:
                self.session.cookies.set('Steam_Language', language, domain=domain)
                self.session.cookies.set('birthtime', '-3333', domain=domain)
                self.session.cookies.set('sessionid', self.session_id, domain=domain)
            self._finalize_login(resp)

            return self.session
        else:
            if resp.get('captcha_needed', False):
                self.captcha_gid = resp['captcha_gid']
                self.captcha_code = ''

                if resp.get('clear_password_field', False):
                    self.password = ''
                    raise webauth.CaptchaRequiredLoginIncorrect(resp['message'])
                else:
                    raise webauth.CaptchaRequired(resp['message'])

            elif resp.get('emailauth_needed', False):
                self.steam_id = webauth.SteamID(resp['emailsteamid'])
                raise webauth.EmailCodeRequired(resp['message'])

            elif resp.get('requires_twofactor', False):
                raise webauth.TwoFactorCodeRequired(resp['message'])

            else:
                self.password = ''
                raise webauth.LoginIncorrect(resp['message'])
