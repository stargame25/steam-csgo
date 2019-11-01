import datetime
import json
import re
from base64 import b64encode
from urllib.parse import urljoin

from bs4 import BeautifulSoup as Bs
from steam import steamid as steamidapi
from steam import webapi
from steam.core.cm import CMServerList
from steam.core.crypto import rsa_publickey, pkcs1v15_encrypt
from steam.webauth import (
    TwoFactorCodeRequired,
    CaptchaRequired,
    CaptchaRequiredLoginIncorrect,
    EmailCodeRequired
)

from .util import csgo_misc, steam_misc
from .webauth import WebAuth


class CSGOApi(object):
    def __init__(self, _api_key=None, _api_domain='csgohelper'):
        self.webclient = None
        self.api_interface = None
        self.session_id = None
        self.api_key = _api_key
        self.api_domain = _api_domain
        self.limited = True
        self.steamid = None
        self.comm_link = None
        self.gamemodes = csgo_misc['compmodes']
        self.team_names = csgo_misc['teams']

    @staticmethod
    def time(date):
        return datetime.datetime.strptime(date.replace("GMT", "").strip(), "%Y-%m-%d %H:%M:%S")

    @staticmethod
    def check_steam_status():
        servers_con = CMServerList()
        servers_con.bootstrap_from_dns()
        return bool(len(servers_con))

    def extract_json(self, content):
        return json.loads(content, encoding='utf8')

    def check_for_new(self, date, check_date):
        if date and not check_date:
            return True
        if self.time(date) > self.time(check_date):
            return True
        return False

    def check_for_error(self, html):
        if html.find("p", {"class": "sectionText"}) or html.find("h3"):
            return True
        else:
            return False

    def login_in(self, username='', password='', timestamp='', captcha='', captcha_gid=-1,
                 email_code='', steam_id='', twofactor_code='', language='english'):
        self.webclient = WebAuth()
        response = self.webclient.login_raw(username, password, timestamp, captcha, captcha_gid,
                                            email_code, steam_id, twofactor_code, language)
        if self.webclient.logged_on:
            self.username = username
        return response

    def main(self):
        self.session_id = self.webclient.session_id
        self.steamid = str(self.webclient.steam_id.as_64)
        self.comm_link = self.webclient.get_(self.webclient.steam_id.community_url).url
        if self.comm_link[-1] != '/':
            self.comm_link += '/'
        elif '/home/' in self.comm_link:
            self.comm_link = self.comm_link.replace('/home/', '/')
        self.load_api_key()
        me = self.load_me_full()
        games = self.load_all_games()
        return (me, games)

    def get_api_key(self):
        resp = self.webclient.get_("https://steamcommunity.com/dev/apikey")
        html = Bs(resp.text, "html.parser")
        if html.find("div", {"id": "bodyContents_lo"}):
            return None
        if html.find("input", {"name": "Revoke"}) is not None:
            return html.find("div", {"id": "bodyContents_ex"}).find_all("p")[0].text.strip().split(' ')[1]
        else:
            self.webclient.session.post("https://steamcommunity.com/dev/registerkey", data={
                "domain": self.api_domain,
                "agreeToTerms": "agreed",
                "sessionid": self.session_id,
                "Submit": "Register"
            })
            return self.get_api_key()

    def load_api_key(self):
        self.limited = True
        self.api_key = self.get_api_key()
        if self.api_key:
            self.limited = False
            self.api_interface = webapi.WebAPI(self.api_key)
        return self.api_key

    def load_all_games(self):
        csgo_games = {}
        for mode in self.gamemodes:
            csgo_games[mode] = self.load_games(mode)
        return csgo_games

    def load_new_games(self, gamemode, date=None):
        continue_token = 0
        games_count = 0
        games = []
        while continue_token is not None:
            match_dict = self.get_games_history(gamemode, self.session_id, continue_token)
            if match_dict and match_dict.get("html"):
                data = self.parse_games(gamemode, match_dict.get('html'))
            else:
                return []
            for game in data:
                if self.check_for_new(game["info"]["date"], date):
                    games.append(game)
                    games_count += 1
            continue_token = match_dict.get("continue_token")
        return games

    def load_games(self, gamemode):
        return self.load_new_games(gamemode)

    def load_me_full(self):
        return {"me": self.load_me(), "matchmaking_data": self.load_matchmaking_data(),
                "cooldown": self.load_cooldown_status()}

    def load_me(self):
        resp = self.webclient.get_(self.comm_link)
        steam_profile = Bs(resp.text, 'html.parser')
        me = {}
        if steam_profile.find("div", {"class": "welcome_header_ctn"}):
            return me
        ban_data = self.load_me_ban_status()
        me['banned'] = ban_data['banned']
        me['VAC'] = ban_data['VAC']
        me['overwatch'] = ban_data['overwatch']
        me['name'] = steam_profile.find('span', {'class': 'actual_persona_name'}).text.strip()
        me['realname'] = steam_profile.find('div', {'class': 'header_real_name ellipsis'}).find('bdi').text.strip()
        if steam_profile.find('div', {'class': 'header_real_name ellipsis'}).find('img'):
            me['country'] = re.findall(r'(\w+)',
                                       steam_profile.find('div',
                                                          {'class': 'header_real_name ellipsis'})
                                       .find('img')['src'])[-2]
        me['icon'] = steam_profile.find('div', {'class': 'playerAvatarAutoSizeInner'}).find('img')['src']
        me['level'] = steam_profile.find('span', {'class': 'friendPlayerLevelNum'}).text.strip()
        me['status'] = steam_profile.find('div', {'class': 'playerAvatar'})['class'][-1]
        return me

    def load_matchmaking_data(self):
        resp = self.webclient.get_(urljoin(self.comm_link, 'gcpd/730/'), params=dict(tab='matchmaking'))
        csgo_profile = Bs(resp.text, 'html.parser')
        ranks = []
        if not csgo_profile.find('div', {'id': 'personaldata_elements_container'}):
            return ranks
        info_tables = csgo_profile.find_all('table', {'class': 'generic_kv_table'})
        for table in info_tables:
            if all(item in table.find("tr").get_text() for item in ["Matchmaking Mode", "Skill Group"]):
                for row in table.find_all("tr")[1:]:
                    comp_info = row.find_all('td')
                    gamemode_info = dict()
                    gamemode_info['gamemode'] = comp_info[0].text.strip()
                    gamemode_info['wins'] = comp_info[1].text.strip()
                    gamemode_info['draws'] = comp_info[2].text.strip()
                    gamemode_info['losses'] = comp_info[3].text.strip()
                    gamemode_info['rank'] = comp_info[4].text.strip()
                    gamemode_info['last_game'] = comp_info[5].text.strip().replace('GMT', '').strip()
                    ranks.append(gamemode_info)
                break
        return ranks

    def load_me_ban_status(self):
        if not self.limited:
            return self.parse_player_ban(self.get_player_ban_status(self.steamid))
        else:
            # develop alternate method for check
            return {'banned': None, 'VAC': None, 'overwatch': None}

    def load_cooldown_status(self):
        resp = self.webclient.get_(urljoin(self.comm_link, 'gcpd/730/'), params=dict(tab='matchmaking'))
        csgo_profile = Bs(resp.text, 'html.parser')
        cooldown = {}
        if not csgo_profile.find("div", {'id': 'personaldata_elements_container'}):
            return cooldown
        info_table = csgo_profile.find_all('table', {'class': 'generic_kv_table'})
        for table in info_table:
            if "Competitive Cooldown Expiration" in table.find("tr").get_text():
                cooldown_info = table.find_all('tr')[1].find_all('td')
                cooldown['expire'] = cooldown_info[0].text.strip()
                cooldown['cd_level'] = cooldown_info[1].text.strip()
                break
        return cooldown

    def get_player_steamid(self, community_links):
        if isinstance(community_links, list):
            out = []
            for i in community_links:
                out.append(steamidapi.from_url(i).as_64)
            return out
        else:
            return str(steamidapi.from_url(community_links).as_64)

    def get_steam_profile_info(self, steamids):
        if isinstance(steamids, list):
            steamids = ", ".join(steamids)
            return self.api_interface.call("ISteamUser.GetPlayerSummaries", steamids=steamids)['response']['players']
        else:
            return self.api_interface.call("ISteamUser.GetPlayerSummaries", steamids=steamids)['response']['players'][0]

    def get_player_ban_status(self, steamids):
        if isinstance(steamids, list):
            steamids = ", ".join(steamids)
            return self.extract_json(self.webclient.get_(urljoin(steam_misc['api'], "ISteamUser/GetPlayerBans/v1/"),
                                                         params=dict(key=self.api_key, steamids=steamids)))['players']
        else:
            return self.extract_json(self.webclient.get_(urljoin(steam_misc['api'], "ISteamUser/GetPlayerBans/v1/"),
                                                         params=dict(key=self.api_key, steamids=steamids))
                                     .text)['players'][0]

    def get_games_history(self, gamemode, session_id, continue_token):
        gamemode = 'matchhistorycompetitive' if gamemode == self.gamemodes[0] else 'matchhistorywingman'
        try:
            resp = self.webclient.get_(urljoin(self.comm_link, 'gcpd/730/'),
                                       params=dict(ajax=1, tab=gamemode,
                                                   continue_token=continue_token,
                                                   sessionid=session_id))
            dict_resp = self.extract_json(resp.text)
            return dict_resp
        except json.decoder.JSONDecodeError:
            pass
        return None

    def get_game_cheats_stat(self, game):
        if self.limited:
            return []
        all_players = game['stat'][self.team_names[0]] + game['stat'][self.team_names[1]]
        payload = self.get_player_ban_status([p['steamid'] for p in all_players])
        return self.parse_cheats_stat(payload, game['info']['date'])

    def parse_games(self, gamemode, html):
        games_set = []
        striped_html = html.strip()
        html = Bs(striped_html, 'html.parser')
        games = html.find_all("tr")
        for game in games:
            columns = game.find_all("table")
            if columns:
                game_info = self.parse_game_info(columns[0])
                game_stat = self.parse_game_stat(columns[1], gamemode)
                games_set.append({"info": game_info, "stat": game_stat})
        return games_set

    def parse_game_info(self, column):
        replay_link = column.find('td', {'class': 'csgo_scoreboard_cell_noborder'})
        options = column.find_all("tr")
        game_info_dict = dict()
        game_info_dict['gamemode'] = self.gamemodes[0] if self.gamemodes[0] in options[0].text.strip() else self.gamemodes[1]
        game_info_dict['map'] = options[0].text.lower().replace(self.gamemodes[0], "").replace(self.gamemodes[1], "").strip()
        game_info_dict['date'] = options[1].text.strip()
        game_info_dict['search_time'] = re.findall(r'\d+:\d+', options[2].text.strip())[0]
        game_info_dict['play_time'] = re.findall(r'\d+:\d+', options[3].text.strip())[0]
        if replay_link:
            game_info_dict['replay'] = replay_link.find('a')['href']
        return game_info_dict

    def parse_game_stat(self, data, gamemode):
        player_counts = 5 if gamemode == self.gamemodes[0] else 2
        leaderboard = data.find_all("tr")
        game_stat_dict = {}
        teams = []
        game_stat_dict['game_score'] = leaderboard[player_counts + 1].find('td').text.strip()
        for i in range(len(self.team_names)):
            team = []
            for j in range(player_counts):
                player_stat = leaderboard[(i * (player_counts + 1)) + 1 + j].find_all("td")
                player_stat_dict = dict()
                player_stat_dict['player_name'] = player_stat[0].find('a', {"class": "linkTitle"}).text.strip()
                player_stat_dict['profile_link'] = player_stat[0].find('a', {"class": "linkTitle"})['href']
                player_stat_dict['steamid'] = str(
                    steamidapi.make_steam64(player_stat[0].find('img')['data-miniprofile']))
                player_stat_dict['player_icon'] = player_stat[0].find('img')['src']
                player_stat_dict['ping'] = player_stat[1].text.strip()
                player_stat_dict['kills'] = player_stat[2].text.strip()
                player_stat_dict['assists'] = player_stat[3].text.strip()
                player_stat_dict['deaths'] = player_stat[4].text.strip()
                player_stat_dict['mvps'] = "0" if len(re.findall(r'\d+', player_stat[5].text.strip())) == 0 else \
                    re.findall(r'\d+', player_stat[5].text.strip())[0]
                player_stat_dict['hs_percent'] = player_stat[6].text.strip()
                player_stat_dict['score'] = player_stat[7].text.strip()
                team.append(player_stat_dict)
            teams.append(team)
        game_stat_dict[self.team_names[0]] = teams[0]
        game_stat_dict[self.team_names[1]] = teams[1]
        game_stat_dict['status'] = self.check_game_status(game_stat_dict)
        return game_stat_dict

    def parse_cheats_stat(self, data, date):
        cheats_stat = []
        for player in data:
            ban = self.parse_player_ban(player, date)
            if ban['banned']:
                cheats_stat.append({**{'steamid': player['SteamId']}, **ban})
        return cheats_stat

    def parse_player_ban(self, data, date=None):
        banned = False
        vac = False
        vac_counts = 0
        overwatch = False
        ov_counts = 0
        after_game = None
        last_ban_date = 0
        if data['VACBanned']:
            banned = True
            vac = True
            vac_counts = data['NumberOfVACBans']
        if data['NumberOfGameBans'] > 0:
            banned = True
            overwatch = True
            ov_counts = data['NumberOfGameBans']
        if banned:
            last_ban_date = data['DaysSinceLastBan']
        if (vac or overwatch) and (date is not None):
            ban_date = datetime.timedelta(days=data['DaysSinceLastBan'])
            game_date = self.time(date)
            now_date = datetime.datetime.now()
            after_game = (now_date - ban_date) > game_date
        return {"banned": banned, "VAC": vac, "VAC_counts": vac_counts, "overwatch": overwatch,
                "ov_counts": ov_counts, "after": after_game, "DaysSinceLastBan": last_ban_date}

    def find_player_team_in_game(self, game, steamid):
        for i in self.team_names:
            for player in game[i]:
                if steamid == player['steamid']:
                    return {'team': i}
        return None

    def check_game_status(self, game):
        score = game['game_score'].split(' : ')
        if score[0] == score[1]:
            return 0
        if self.find_player_team_in_game(game, self.steamid)['team'] == self.team_names[0]:
            if int(score[0]) > int(score[1]):
                return 1
            else:
                return -1
        else:
            if int(score[0]) < int(score[1]):
                return 1
            else:
                return -1

    def cli_login_in(self, username, password):
        rsa = WebAuth.get_rsa(username)
        key = rsa_publickey(int(rsa['publickey_mod'], 16),
                            int(rsa['publickey_exp'], 16))
        try:
            self.login_in(username, b64encode(pkcs1v15_encrypt(key, password.encode('ascii'))), rsa['timestamp'])
        except TwoFactorCodeRequired:
            code = input("twofactor: ")
            self.login_in(username, b64encode(pkcs1v15_encrypt(key, password.encode('ascii'))), rsa['timestamp'],
                          twofactor_code=code)


if __name__ == '__main__':
    username = input("username: ")
    password = input("password: ")
    cli = CSGOApi()
    cli.cli_login_in(username, password)
    cli.load_api_key()
    cli.main()
