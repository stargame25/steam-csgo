# steam-csgo
This module is wrapper of steam library (https://github.com/ValvePython/steam). 
Library use BeautifulSoup and Requests mechanics to parse and present as array of data.


## How to use
To use this start with installing:
1. Download any release (recommended) or branch you want to explore
2. Unpack and install with command `pip install .`
3. To import module in your project simply write 
```python
import steam_csgo
```
4. Now you able to use CSGOApi and WebAuth (modified) classes

### Example
#### For CLI
```python
from steam_csgo import CSGOApi


username = input("username: ")
password = input("password: ")
cli = CSGOApi(username)
cli.cli_login_in(password) # if error occurred exception will be called
me, games = cli.main() # used to response most important info
```
#### For include
```python
from steam_csgo import CSGOApi


user_object = CSGOApi(username)
rsa = CSGOApi.get_rsa(username)
# password should be crypted before passing, if error occurred exception will be called
# you can pass params such as: captcha code, captcha id, email code (steam guard), two-factor code, language
loggin_status = user_object.login_in(username, password, rsa['timestamp']) 
me, games = user_object.main() # used to response most important info
```

#### More info
For more flexible way to get certain info about user (player) all methods related to full auto parse starts with load prefix
- `load_all_games` - used to load dict for games for all gamemodes (competitive, wingman)
- `load_games`- used to load all games for specific gamemodes
- `load_new_games` - used to load new games until date which should be specified
- `load_me_full` - used to load user steam profile data, matchmaking data and in-game cooldown status
- `load_me` - used to load user steam profile data
- `load_matchmaking_data` - used to load user in-game matchmaking data
- `load_cooldown_status` - used to load user in-game cooldown status
- `load_me_ban_status` - check user permanent ban status (VAC, overwatch ban statuses)
### Important
Be aware that module uses steam web API features, that require API key, 
which only "verified" account (account that spend at lease 5$) can receive.
