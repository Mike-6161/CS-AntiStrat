import discord
from discord import app_commands
from discord.ext import commands
from python_graphql_client import GraphqlClient
from dotenv import load_dotenv
import os
import asyncio


def get_team_opponent_stats(team: str, season: int, tier: str):
    client = GraphqlClient(endpoint="https://stats.csconfederation.com/graphql")

    query = """
    query MyQuery {
      findManyMatch(
        where: {season: {equals: %s}, tier: {equals: %s}, matchDay: {not: {equals: ""}}, matchType: {equals: Regulation}}
      ) {
        teamStats {
          name
          score
        }
        mapName
      }
    } """ % (season, tier)

    matches = client.execute(query=query)["data"]["findManyMatch"]

    win_loss_stats = {}
    team_map_opponents = {}

    # Get each team's round wins and losses, and map wins and losses
    for match in matches:
        # Handle the first team
        if match["teamStats"][0]["name"] not in win_loss_stats.keys():
            win_loss_stats[match["teamStats"][0]["name"]] = {"wins": 0, "losses": 0, "easy_wins": 0, "hard_losses": 0, "close": 0, "round_wins": 0, "round_losses": 0}

        win_loss_stats[match["teamStats"][0]["name"]]["round_wins"] += match["teamStats"][0]["score"]
        win_loss_stats[match["teamStats"][0]["name"]]["round_losses"] += match["teamStats"][1]["score"]

        if match["teamStats"][0]["score"] > match["teamStats"][1]["score"]:
            win_loss_stats[match["teamStats"][0]["name"]]["wins"] += 1

            if match["teamStats"][1]["score"] >= 10:
                win_loss_stats[match["teamStats"][0]["name"]]["close"] += 1
            else:
                win_loss_stats[match["teamStats"][0]["name"]]["easy_wins"] += 1
        else:
            win_loss_stats[match["teamStats"][0]["name"]]["losses"] += 1

            if match["teamStats"][0]["score"] >= 10:
                win_loss_stats[match["teamStats"][0]["name"]]["close"] += 1
            else:
                win_loss_stats[match["teamStats"][0]["name"]]["hard_losses"] += 1

        # Handle the second team
        if match["teamStats"][1]["name"] not in win_loss_stats.keys():
            win_loss_stats[match["teamStats"][1]["name"]] = {"wins": 0, "losses": 0, "easy_wins": 0, "hard_losses": 0, "close": 0, "round_wins": 0, "round_losses": 0}

        win_loss_stats[match["teamStats"][1]["name"]]["round_wins"] += match["teamStats"][1]["score"]
        win_loss_stats[match["teamStats"][1]["name"]]["round_losses"] += match["teamStats"][0]["score"]

        if match["teamStats"][1]["score"] > match["teamStats"][0]["score"]:
            win_loss_stats[match["teamStats"][1]["name"]]["wins"] += 1
        else:
            win_loss_stats[match["teamStats"][1]["name"]]["losses"] += 1

        # Add the opponent to the list of opponents for the current map
        if match["teamStats"][0]["name"] == team or match["teamStats"][1]["name"] == team:
            if match ["mapName"] not in team_map_opponents.keys():
                team_map_opponents[match["mapName"]] = {"opponents": [], "wins": 0, "losses": 0, "round_wins": 0, "round_losses": 0}

            # Get the opponent of the team in question, if applicable
            if match["teamStats"][0]["name"] == team:
                team_map_opponents[match["mapName"]]["opponents"].append(match["teamStats"][1]["name"])

                team_map_opponents[match["mapName"]]["round_wins"] += match["teamStats"][0]["score"]
                team_map_opponents[match["mapName"]]["round_losses"] += match["teamStats"][1]["score"]

                if match["teamStats"][0]["score"] > match["teamStats"][1]["score"]:
                    team_map_opponents[match["mapName"]]["wins"] += 1
                else:
                    team_map_opponents[match["mapName"]]["losses"] += 1

            if match["teamStats"][1]["name"] == team:
                team_map_opponents[match["mapName"]]["opponents"].append(match["teamStats"][0]["name"])

                team_map_opponents[match["mapName"]]["round_wins"] += match["teamStats"][1]["score"]
                team_map_opponents[match["mapName"]]["round_losses"] += match["teamStats"][0]["score"]

                if match["teamStats"][1]["score"] > match["teamStats"][0]["score"]:
                    team_map_opponents[match["mapName"]]["wins"] += 1
                else:
                    team_map_opponents[match["mapName"]]["losses"] += 1

    title = "## " + team + "\n"
    title += "**" + str(win_loss_stats[team]["wins"]) + "-" + str(win_loss_stats[team]["losses"]) + "**    "\
             "*" + str(win_loss_stats[team]["easy_wins"]) + "-" + str(win_loss_stats[team]["close"]) + "-" + str(win_loss_stats[team]["hard_losses"]) + "*      "
    title += str(round(win_loss_stats[team]["round_wins"] / (win_loss_stats[team]["round_wins"] +
                                                             win_loss_stats[team]["round_losses"]), 2)) + " RWP"

    title += "\n```Team Map Stats: \n"

    message = title + "          Wins      Losses    RWP       Avg Opp Rwp\n"

    for map_name in team_map_opponents.keys():
        formatted_map_name = map_name
        if "de_" in map_name:
            formatted_map_name = map_name[3].upper() + map_name[4:len(map_name)]

        message += formatted_map_name + " " * (10 - len(formatted_map_name))
        message += str(team_map_opponents[map_name]["wins"]) + " " * (10 - len(str(team_map_opponents[map_name]["wins"])))
        message += str(team_map_opponents[map_name]["losses"]) + " " * (10 - len(str(team_map_opponents[map_name]["losses"])))

        rwp = round(team_map_opponents[map_name]["round_wins"] / (team_map_opponents[map_name]["round_wins"] +
                                                                  team_map_opponents[map_name]["round_losses"]), 2)

        message += str(rwp) + " " * (10 - len(str(rwp)))

        avg_opp_round_wins = 0
        avg_opp_round_losses = 0

        for opponent in team_map_opponents[map_name]["opponents"]:
            avg_opp_round_wins += win_loss_stats[opponent]["round_wins"]
            avg_opp_round_losses += win_loss_stats[opponent]["round_losses"]

        aorwp = round(avg_opp_round_wins / (avg_opp_round_losses + avg_opp_round_wins), 2)

        message += str(aorwp) + " " * (10 - len(str(aorwp))) + "\n"

    return message


def get_team_map_bans(team: str, season: int):
    client = GraphqlClient(endpoint="https://core.csconfederation.com/graphql")

    query = """
    query myquery	 {
        team(teamName: "%s") {
            id
        }
    }
    """ % team

    team_id = client.execute(query=query)["data"]["team"]["id"]

    query = """
    query myquery	 {
        matches(season: %s, teamId: "%s") {
            lobby {
                mapBans {
                    team {
                        name
                        id
                    }
                    map
                    number
                }
            }
        }
    } """ % (season, team_id)

    matches = client.execute(query=query)["data"]["matches"]

    ban_stats = {}

    for match in matches:
        if match["lobby"] is None or match["lobby"]["mapBans"] == []:
            continue

        for ban in match["lobby"]["mapBans"]:
            if ban["team"]["name"] == team:
                if ban["map"] not in ban_stats.keys():
                    ban_stats[ban["map"]] = []

                ban_stats[ban["map"]].append((ban["number"] + 1) // 2)

    message = "\nMap Ban Stats:\n          # Banned  Avg Ban Round\n"

    for map_name in ban_stats.keys():
        if not ban_stats[map_name]:
            continue

        formatted_map_name = map_name
        if "de_" in map_name:
            formatted_map_name = map_name[3].upper() + map_name[4:len(map_name)]

        message += formatted_map_name + " " * (10 - len(formatted_map_name))
        message += str(len(ban_stats[map_name])) + " " * (10 - len(str(len(ban_stats[map_name]))))
        avg = round(sum(ban_stats[map_name]) / len(ban_stats[map_name]), 2)
        message += str(avg) + "\n"

    return message


def get_team_players_map_stats(team: str, season: int):
    """
    Queries core and stats APIs to get stats for currently rostered players on the given team

    :param season: CSC Season number
    :param team: Team name
    :return: Formatted string to send to discord
    """

    client = GraphqlClient(endpoint="https://core.csconfederation.com/graphql")

    query = """
        query myquery	 {
            team(teamName: %s){players{name, type}}
        }
        """ % ("\"" + team + "\"")

    data = client.execute(query=query)["data"]["team"]["players"]

    active_players = []
    sub_players = []

    for player in data:
        if "SIGNED" in player["type"]:
            active_players.append(player["name"])
        if "TEMP" in player["type"]:
            sub_players.append(player["name"])

    client = GraphqlClient(endpoint="https://stats.csconfederation.com/graphql")

    player_data = {}

    for player in active_players:
        query = """
               query MyQuery {
                  findManyMatch( 
                     where: {matchType: {equals: Regulation}, season: {equals: %s}, matchDay: {not: {equals: ""}}, matchStats: {some: {name: {equals: "%s"}}}}
                  ) {
                     mapName
                     matchStats(where: {name: {equals: "%s"}, AND: {side: {equals: 4}}}) {
                        rating
                     }
                  }
                }
               """ % (season, player, player)

        data = client.execute(query=query)

        player_data[player] = data["data"]["findManyMatch"]

    maps = []
    player_stats = {}

    for player in player_data.keys():
        player_stats[player] = {}
        for match in player_data[player]:
            if match["mapName"] not in player_stats[player].keys():
                player_stats[player][match["mapName"]] = [0, 0]

            player_stats[player][match["mapName"]][0] += match["matchStats"][0]["rating"]
            player_stats[player][match["mapName"]][1] += 1

            if match["mapName"] not in maps:
                maps.append(match["mapName"])

    info_message = "\nPlayer Map Stats:\n               "
    players_message = ""

    for player in player_stats.keys():
        if player in sub_players:
            players_message = players_message + player + " (S)" + (11 - len(player)) * " "
        else:
            players_message = players_message + player + (15 - len(player)) * " "
        for map_name in maps:
            if player == list(player_stats.keys())[0]:
                if "de_" in map_name:
                    formatted_map_name = map_name[3].upper() + map_name[4:len(map_name)]

                info_message = info_message + formatted_map_name + (10 - len(formatted_map_name)) * " "

            if map_name in player_stats[player].keys():
                players_message = \
                    players_message + \
                    str(round((player_stats[player][map_name][0] / player_stats[player][map_name][1]), 2)) + \
                    (10 - len(
                        str(round(player_stats[player][map_name][0] / player_stats[player][map_name][1], 2)))) * " "
            else:
                players_message = players_message + "-         "

        players_message = players_message + "\n"

    info_message = info_message + "\n" + players_message

    return info_message


# Stats: {"apiName": "displayName", ...}
def get_team_players_various_stats(team: str, season: int, stats: dict):
    """
    Queries core and stats APIs to get overall awp stats for currently rostered players on the given team

    :param team: Team name
    :param season: CSC Season
    :param stats: Dictionary with api stat keys and display stat values {"apiName": "displayName", ...}
    :return: Formatted string to send to discord
    """

    client = GraphqlClient(endpoint="https://core.csconfederation.com/graphql")

    query = """
            query myquery	 {
                team(teamName: %s){players{name, type}}
            }
            """ % ("\"" + team + "\"")

    data = client.execute(query=query)["data"]["team"]["players"]

    active_players = []
    sub_players = []

    for player in data:
        if "SIGNED" in player["type"]:
            active_players.append(player["name"])
        if "TEMP" in player["type"]:
            sub_players.append(player["name"])

    client = GraphqlClient(endpoint="https://stats.csconfederation.com/graphql")

    api_string = ", ".join(list(stats.keys()))

    stats_names = " " * 14

    for stat in stats.keys():
        stats_names += stats[stat] + " " * (10 - len(stats[stat]))

    stats_names += "\n"

    players = ""

    for player in active_players:
        query = """
        query MyQuery {
            playerSeasonStats(name: "%s", season: %s, matchType: "Regulation") {
                %s
            }
        }""" % (player, season, api_string)

        data = client.execute(query=query)

        if 'errors' in data.keys():
            continue

        if player in sub_players:
            player += " (S)"

        players = players + player + (14 - len(player)) * " "

        for stat in stats.keys():
            temp = str(round(data["data"]["playerSeasonStats"][stat], 2))
            players = players + temp + (10 - len(temp)) * " "

        players = players + "\n"

    return stats_names + players + "```"


def get_team_summary_stats(franchise: str, season: int, tier: str):
    franchise = franchise.upper()
    if franchise == "DB":
        franchise = "dB"

    tier = tier[0:1].upper() + tier[1:].lower()

    # Get team name from franchise name and tier
    client = GraphqlClient(endpoint="https://core.csconfederation.com/graphql")

    query = """
        query myquery {
            franchises(active: true) {
                teams {
                    tier {
                        name
                    }
                    name
                }
                prefix
            }
        }
        """

    franchises = client.execute(query=query)["data"]["franchises"]

    team = ""

    for f in franchises:
        if f["prefix"] == franchise:
            for t in f["teams"]:
                if t["tier"]["name"] == tier:
                    team = t["name"]

    if team == "":
        return "Invalid Team and / or Tier Name"

    message = get_team_opponent_stats(team, season, tier)
    message += get_team_map_bans(team, season)
    message += get_team_players_map_stats(team, season)
    message += "\nMisc Stats: \n"
    message += get_team_players_various_stats(team, season, {"ef": "EF", "fAssists": "FAss", "util": "Util", "awpR": "Awp/r", "savesR": "Saves/r", "odr": "ODR", "odaR": "ODA/r"})

    message += f"\n-# All stats are from season {season}, roster information is current from core."

    return message


def get_team_advanced_summary_stats(franchise: str, season: int, tier: str):
    franchise = franchise.upper()
    if franchise == "DB":
        franchise = "dB"

    tier = tier[0:1].upper() + tier[1:].lower()

    # Get team name from franchise name and tier
    client = GraphqlClient(endpoint="https://core.csconfederation.com/graphql")

    query = """
        query myquery {
            franchises(active: true) {
                teams {
                    tier {
                        name
                    }
                    name
                }
                prefix
            }
        }
        """

    franchises = client.execute(query=query)["data"]["franchises"]

    team = ""

    for f in franchises:
        if f["prefix"] == franchise:
            for t in f["teams"]:
                if t["tier"]["name"] == tier:
                    team = t["name"]

    if team == "":
        return "Invalid Team and / or Tier Name"

    message = get_team_opponent_stats(team, season, tier)
    message += get_team_map_bans(team, season)
    message += get_team_players_map_stats(team, season)
    message += "Fragging Stats: \n"
    message += get_team_players_various_stats(team, season, {"rating": "Rating", "adr": "ADR", "kast": "KAST", "hs": "HS%", "tradesR": "Trades/r", "multiR": "Multi/r", "adp": "ADP"})
    message += "Entry Stats: \n"
    message += get_team_players_various_stats(team, season, {"odaR": "ODA/r", "odr": "ODR", "tRatio": "TRatio"})
    message += "Utility Stats: \n"
    message += get_team_players_various_stats(team, season, {"util": "Util", "ef": "EF", "fAssists": "FAss", "utilDmg": "UD"})

    message_2 = "Awp Stats: \n"
    message_2 += get_team_players_various_stats(team, season, {"awpR": "Awp/r", "savesR": "Saves/r", "saveRate": "SRate"})
    message_2 += "Clutch Stats: \n"
    message_2 += get_team_players_various_stats(team, season, {"clutchR": "Clutch/r", "cl_1": "1v1", "cl_2": "1v2", "cl_3": "1v3", "cl_4": "1v4", "cl_5": "1v5"})

    message_2 += "*Map and player stats are pulled from the season given, roster information is current from core.*"

    return (message, message_2)

# def get_team_match_history(franchise: str, season: int, tier: str):



if __name__ == "__main__":

    load_dotenv()

    intents = discord.Intents.default()
    intents.message_content = True

    bot = commands.Bot(command_prefix='!', description='CSC Scouting Bot', intents=intents)

    token = os.getenv("BOT_TOKEN")

    # Get franchise prefixes
    client = GraphqlClient(endpoint="https://core.csconfederation.com/graphql")

    query = """
            query myquery {
                franchises(active: true) {
                    prefix
                }
            }
            """

    franchises = client.execute(query=query)["data"]["franchises"]

    franchise_choices = []

    for f in franchises:
        franchise_choices.append(app_commands.Choice(name=f['prefix'], value=f['prefix']))

    @bot.event
    async def on_ready():
        print("Bot Started")
        await bot.change_presence(activity=discord.Game('/scout'))

        try:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(e)

    @bot.tree.command(name="scout", description="Get team / players stats for a team.")
    @app_commands.choices(franchise=franchise_choices)
    @app_commands.choices(tier=[
        app_commands.Choice(name="Recruit", value="Recruit"),
        app_commands.Choice(name="Prospect", value="Prospect"),
        app_commands.Choice(name="Contender", value="Contender"),
        app_commands.Choice(name="Challenger", value="Challenger"),
        app_commands.Choice(name="Elite", value="Elite"),
        app_commands.Choice(name="Premier", value="Premier")
    ])
    async def scout(interaction: discord.Interaction, franchise: str, tier: str):

        await interaction.response.defer()
        await interaction.followup.send(get_team_summary_stats(franchise, int(14), tier))


    # @bot.tree.command(name="matches", description="Get team match history.")
    # @app_commands.choices(franchise=franchise_choices)
    # @app_commands.choices(tier=[
    #     app_commands.Choice(name="Recruit", value="Recruit"),
    #     app_commands.Choice(name="Prospect", value="Prospect"),
    #     app_commands.Choice(name="Contender", value="Contender"),
    #     app_commands.Choice(name="Challenger", value="Challenger"),
    #     app_commands.Choice(name="Elite", value="Elite"),
    #     app_commands.Choice(name="Premier", value="Premier")
    # ])
    # async def scout(interaction: discord.Interaction, franchise: str, tier: str):
    #
    #     await interaction.response.defer()
    #     await interaction.followup.send(get_team_summary_stats(franchise, int(14), tier))

    bot.run(token)

