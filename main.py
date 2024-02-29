from awpy.parser import DemoParser
from awpy.visualization import plot
import datetime
import pdfkit
import jinja2
import json
from matplotlib import pyplot as plt
from matplotlib import pylab
import pypdf
import pathlib
from discord_webhook import DiscordWebhook
import io
import os
import zipfile
from typing import Tuple
from boto3 import client as Client
from dotenv import load_dotenv
from python_graphql_client import GraphqlClient

# Load environment file with region, key, and secret
load_dotenv(".env")


def fetch_demos(
        season: int, team: str, include_preseason: bool = False
) -> Tuple[str, int]:
    """
    Fetches all demos for a team from a given season

    :param season: Season to get demos from
    :param team: Team to fetch demos for
    :param include_preseason: Whether to download preseason matches or not
    :return: Tuple containing directory all demos were downloaded in, and how many demos were fetched
    """

    # Create base directory
    dir = os.path.join("temp-demos", team)
    if not os.path.exists(dir):
        os.makedirs(dir)

    # Get list of demos from demos.csconfederation.com
    bucket = "cscdemos"
    client = Client(
        "s3",
        endpoint_url=f"https://{os.environ['SPACES_REGION']}.digitaloceanspaces.com",
        region_name=os.environ["SPACES_REGION"],
        aws_access_key_id=os.environ["SPACES_KEY"],
        aws_secret_access_key=os.environ["SPACES_SECRET"],
    )

    # Get all match day demos
    all_demos = client.list_objects_v2(
        Bucket=bucket,
        Prefix=f"s{season:02d}/M",
    )["Contents"]

    # Append all preseason demos
    if include_preseason:
        all_demos.append(
            client.list_objects_v2(
                Bucket=bucket,
                Prefix=f"s{season:02d}/P",
            )["Contents"]
        )

    # Filter demos to only team demos and remove any directories (S3 includes the buckets for some reason in the
    # results)
    demo_paths = [
        x["Key"] for x in all_demos if team in x["Key"] and ".dem" in x["Key"]
    ]
    for demo_path in demo_paths:
        filename = os.path.join(dir, os.path.basename(demo_path))
        file = client.get_object(Bucket=bucket, Key=demo_path)["Body"].read()

        with (
            zipfile.ZipFile(io.BytesIO(file)) as zipped,
            open(filename, "wb") as output,
        ):
            with zipped.open(zipped.filelist[0]) as f:
                output.write(f.read())

    return dir, len(demo_paths)


def get_team_demo_file_paths(team: str, folder: str, use_file_names: bool):
    """
    Gets all demos in which the given team played in

    :param team: Team name to get demo files for
    :param folder: File path to folder containing demos
    :param use_file_names: Whether to use the names of the demo files to check if the team played in that demo
    :return: A list containing strings with file paths to all demos for the given team
    """
    file_paths = []
    if use_file_names:
        for file in os.listdir(folder):
            if (
                    file[(len(file) - 3): len(file)] == "dem"
                    and team.replace(" ", "") in file
            ):
                file_paths.append(folder + "/" + file)

    return file_paths


def parse_and_sort_by_map(files: list, file_folder: str):
    """
    Sorts the demo files into a dictionary based on map, and parses any unparsed demos into a .json file

    :param files: A list of file paths to demo files
    :param file_folder: The file path to the folder containing the demos
    :return: A dictionary where keys are each map played in the demos listed, and values are a list of the demos for
    each map
    """
    maps = {}
    for file in files:
        # if demo is already parsed
        print(file[0: (len(file) - 3)] + "json")
        if os.path.isfile(file[0: (len(file) - 3)] + "json"):
            f = open((file[0: (len(file) - 3)] + "json"))
            data = json.load(f)
            f.close()
        # else parse the demo
        else:
            print("Parsing")
            demo_parser = DemoParser(
                demofile=file,
                parse_rate=128,
                buy_style="hltv",
                parse_kill_frames=True,
                outpath=file_folder,
            )

            data = demo_parser.parse(clean=True)

        if data["mapName"] in maps.keys():
            maps[data["mapName"]].append(file[0: (len(file) - 3)] + "json")
        else:
            maps[data["mapName"]] = [file[0: (len(file) - 3)] + "json"]

    return maps


def get_scouting_info(team: str, map_files: dict):
    """
    Gets opponents and position and grenade info for the first 12 seconds of rounds for many types of buys for T and CT

    :param team: Name of team
    :param map_files: Dictionary of maps and their demo files
    :return: A list of opponents, position info for both sides for all types of buys 12 seconds into the rounds, and
    grenade info for both sides for all types of buys for all grenades thrown before 12 seconds into the rounds
    """
    position_info = {}
    grenades_info = {}
    opponents = {}
    for map_name in map_files.keys():
        map_opponents = []
        positions = {
            "t": {
                "Pistol": {},
                "Full Eco": {},
                "Semi Eco": {},
                "Semi Buy": {},
                "Full Buy": {},
            },
            "ct": {
                "Pistol": {},
                "Full Eco": {},
                "Semi Eco": {},
                "Semi Buy": {},
                "Full Buy": {},
            },
        }
        grenades = {
            "t": {
                "Pistol": {},
                "Full Eco": {},
                "Semi Eco": {},
                "Semi Buy": {},
                "Full Buy": {},
            },
            "ct": {
                "Pistol": {},
                "Full Eco": {},
                "Semi Eco": {},
                "Semi Buy": {},
                "Full Buy": {},
            },
        }

        side = ""

        for match in map_files[map_name]:
            f = open(match)
            data = json.load(f)
            f.close()

            tickrate = data["tickRate"]

            for r in data["gameRounds"]:
                if r["ctTeam"] == team:
                    side = "ct"
                else:
                    side = "t"

                if r["roundNum"] == 1:
                    if side == "ct":
                        map_opponents.append(r["tTeam"])
                    else:
                        map_opponents.append(r["ctTeam"])

                if r["roundNum"] in [1, 16]:
                    buy = "Pistol"
                else:
                    buy = r[side + "BuyType"]

                start_tick = r["freezeTimeEndTick"]

                for f in r["frames"]:
                    if (f["tick"] - start_tick) / tickrate > 12:
                        for p in f[side]["players"]:
                            if p["name"] not in positions[side][buy].keys():
                                positions[side][buy][p["name"]] = []

                            positions[side][buy][p["name"]].append(
                                {"x": p["x"], "y": p["y"], "z": p["z"]}
                            )

                        break

                for g in r["grenades"]:
                    if g["throwSeconds"] <= 12 and g["throwerSide"] == side.upper():
                        if g["throwerName"] not in grenades[side][buy].keys():
                            grenades[side][buy][g["throwerName"]] = []

                        grenades[side][buy][g["throwerName"]].append(
                            {
                                "type": g["grenadeType"],
                                "X1": g["throwerX"],
                                "Y1": g["throwerY"],
                                "Z1": g["throwerZ"],
                                "X2": g["grenadeX"],
                                "Y2": g["grenadeY"],
                                "Z2": g["grenadeZ"],
                            }
                        )

            if side == "ct":
                map_opponents[-1] += " (" + str(r["endCTScore"]) + "-" + str(r["endTScore"]) + ")"
            else:
                map_opponents[-1] += " (" + str(r["endTScore"]) + "-" + str(r["endCTScore"]) + ")"

        position_info[map_name] = positions
        grenades_info[map_name] = grenades
        opponents[map_name] = map_opponents

    return opponents, position_info, grenades_info


# map_position_info: {"t": {"Pistol": player_positions, "Full Eco": {}, "Semi Eco": {}, ...}, "ct": {}}
def get_map_buy_pictures(
        map_name: str, map_position_info: dict, grenades_info: dict, players
):
    """
    Saves plots with player and grenade positions 12 seconds into every round for each buy type for each side

    :param map_name: Name of map
    :param map_position_info: Dictionary with positions for each player on the given map 12 seconds into each round
    :param grenades_info: Dictionary with grenade trajectories for grenades thrown in the first 12 seconds of every
    round for the given team, on the given map
    :param players: List of all players plotted so far. Used to keep colors on plots for players consistent
    :return: Updated list of players plotted so far
    """
    for side in map_position_info.keys():
        for buy in map_position_info[side].keys():
            figure, axes, players = get_single_plot(
                map_name,
                map_position_info[side][buy],
                grenades_info[side][buy],
                players,
            )

            plt.savefig(
                "./temp-images/" + side + "_" + buy + ".png",
                bbox_inches="tight",
                dpi=300,
            )

            if side == "ct" and buy == "Full Buy":
                handles, labels = plt.gca().get_legend_handles_labels()
                by_label = dict(zip(labels, handles))
                fig_legend = pylab.figure(figsize=(1.5, 1.3))
                fig_legend.legend(by_label.values(), by_label.keys())
                # pylab.figlegend(*axes.get_legend_handles_labels())

                fig_legend.savefig(
                    "./temp-images/legend.png", bbox_inches="tight", dpi=300
                )
                plt.close()

            plt.close()

    return players


# player positions: {player1: [{"x": 0, "y": 0, "z": 0}, ...], player2: [], ...}
def get_single_plot(
        map_name: str, player_positions: dict, grenades: dict, players: list
):
    """
    Creates and saves a plot with player positions and grenade trajectories

    :param map_name: Name of map
    :param player_positions: Dictionary with a list of positions for each player
    :param grenades: Dictionary with a list of grenades thrown for each player
    :param players: List of players plotted so far. Used to keep colors on plots for players consistent
    :return: The figure and axes for the plot, and an updated list of plotted players
    """
    figure, axes = plot.plot_map(map_name=map_name, dark=False)

    total_dots = 0

    for key in player_positions.keys():
        total_dots += len(player_positions[key])

    if map_name in ("de_vertigo", "de_nuke"):
        if total_dots > 50:
            dot_size = 10
        else:
            dot_size = 10
    else:
        if total_dots > 50:
            dot_size = 40
        else:
            dot_size = 40

    for player in grenades.keys():
        if player not in players:
            players.append(player)
        for grenade in grenades[player]:
            if grenade["type"] == "Decoy Grenade":
                continue

            if map_name not in ("de_vertigo", "de_nuke"):
                x1, y1, z1 = plot.position_transform_all(
                    map_name, (grenade["X1"], grenade["Y1"], grenade["Z1"])
                )
                x2, y2, z2 = plot.position_transform_all(
                    map_name, (grenade["X2"], grenade["Y2"], grenade["Z2"])
                )
            elif map_name == "de_vertigo":
                # Don't plot a grenade that went off the map
                if grenade["Z2"] < 10000:
                    continue

                x1, y1, z1 = plot.position_transform_all(
                    map_name, (grenade["X1"], grenade["Y1"], grenade["Z2"])
                )
                x2, y2, z2 = plot.position_transform_all(
                    map_name, (grenade["X2"], grenade["Y2"], grenade["Z2"])
                )
            else:
                x1, y1, z1 = plot.position_transform_all(
                    map_name, (grenade["X1"], grenade["Y1"], grenade["Z2"])
                )
                x2, y2, z2 = plot.position_transform_all(
                    map_name, (grenade["X2"], grenade["Y2"], grenade["Z2"])
                )

            # From awpy.visualization.plot.plot_nades()
            g_color = {
                "Incendiary Grenade": "red",
                "Molotov": "red",
                "Smoke Grenade": "gray",
                "HE Grenade": "green",
                "Flashbang": "gold",
            }[grenade["type"]]

            axes.plot(
                [x1, x2], [y1, y2], color=("C" + str(players.index(player))), alpha=0.1
            )
            axes.scatter(x2, y2, color=g_color, s=dot_size, alpha=0.6, marker="x")

    for player in player_positions.keys():
        if player not in players:
            players.append(player)
        for position in player_positions[player]:
            x, y, z = plot.position_transform_all(
                map_name, (position["x"], position["y"], position["z"])
            )

            axes.scatter(
                x,
                y,
                color=("C" + str(players.index(player))),
                label=player,
                s=dot_size,
                zorder=100,
            )

    axes.get_xaxis().set_visible(b=False)
    axes.get_yaxis().set_visible(b=False)

    figure.set_size_inches(10, 10)

    return figure, axes, players


def to_pdf(team: str, map_name: str, opponents: str, images: dict, output_file: str):
    """
    Creates a pdf based on a html template, and list of map images

    :param team: Name of team
    :param map_name: Name of map
    :param opponents: List of opponents team has played on map
    :param images: List of file paths to images for the pdf
    :param output_file: File path for pdf output
    :return: Nothing
    """
    template_loader = jinja2.FileSystemLoader("./")
    template_env = jinja2.Environment(loader=template_loader)

    path = str(pathlib.Path(__file__).parent.resolve())

    context = {
                  "Team": team,
                  "Map": map_name,
                  "Opponents": opponents,
                  "Date": datetime.datetime.now().date,
                  "Legend": (path + "/temp-images/legend.png"),
              } | images

    template = template_env.get_template("map-template.html")
    output_text = template.render(context)

    if map_name in ("de_vertigo", "de_nuke"):
        page_height = 400
    else:
        page_height = 270

    config = pdfkit.configuration(
        wkhtmltopdf="C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe"
    )
    pdfkit.from_string(
        output_text,
        output_file,
        configuration=config,
        options={
            "enable-local-file-access": "",
            "page-height": page_height,
            "page-width": 400,
        },
        css="map-template.css",
    )


def get_scouting_report(team: str, file_path: str):
    """
    Creates a pdf with player positions 12 seconds into every round, sorted by side and team buy type.

    :param team: The team to create the pdf for
    :param file_path: File path to folder with demos
    :return: Nothing
    """
    demo_files = get_team_demo_file_paths(team, file_path, True)
    sorted_json_files = parse_and_sort_by_map(demo_files, file_path)
    opponents, position_info, grenades_info = get_scouting_info(team, sorted_json_files)

    path = str(pathlib.Path(__file__).parent.resolve())

    images = {
        "t_Pistol": path + "/temp-images/t_Pistol.png",
        "t_FullEco": path + "/temp-images/t_Full Eco.png",
        "t_SemiEco": path + "/temp-images/t_Semi Eco.png",
        "t_SemiBuy": path + "/temp-images/t_Semi Buy.png",
        "t_FullBuy": path + "/temp-images/t_Full Buy.png",
        "ct_Pistol": path + "/temp-images/ct_Pistol.png",
        "ct_FullEco": path + "/temp-images/ct_Full Eco.png",
        "ct_SemiEco": path + "/temp-images/ct_Semi Eco.png",
        "ct_SemiBuy": path + "/temp-images/ct_Semi Buy.png",
        "ct_FullBuy": path + "/temp-images/ct_Full Buy.png",
    }

    merger = pypdf.PdfMerger()

    players = []

    for m in opponents.keys():
        players = get_map_buy_pictures(m, position_info[m], grenades_info[m], players)

        opps = ", ".join([str(elem) for elem in opponents[m]])

        to_pdf(team, m, opps, images, "./temp-pdfs/" + m + ".pdf")

        merger.append("./temp-pdfs/" + m + ".pdf")

    merger.write("output/" + team + "_scouting.pdf")
    merger.close()


def get_team_map_win_info(team: str, file_path: str, season: int):
    """
    Gets Win-Loss, RWP, and OARWP information for a given team on each map they have played

    :param season: CSC Season num
    :param team: Name of team
    :param file_path: File path to folder with demos
    :return: A list with strings containing the map info for each map
    """
    demo_files = get_team_demo_file_paths(team, file_path, True)
    sorted_json_files = parse_and_sort_by_map(demo_files, file_path)

    team_win_info = []

    for map in sorted_json_files.keys():
        wins = 0
        losses = 0
        round_wins = 0
        round_losses = 0

        opp_round_wins = 0
        opp_round_losses = 0

        for match in sorted_json_files[map]:
            file = open(match)
            data = json.load(file)
            file.close()

            if data["gameRounds"][0]["ctTeam"] == team:
                opp_team = data["gameRounds"][0]["tTeam"]
            else:
                opp_team = data["gameRounds"][0]["ctTeam"]

            for r in data["gameRounds"]:
                if r["winningTeam"] == team:
                    round_wins += 1
                else:
                    round_losses += 1

            if r["endTScore"] > r["endCTScore"] and r["tTeam"] == team:
                wins += 1
            elif r["endTScore"] < r["endCTScore"] and r["tTeam"] == team:
                losses += 1
            elif r["endTScore"] > r["endCTScore"] and r["ctTeam"] == team:
                losses += 1
            elif r["endTScore"] < r["endCTScore"] and r["ctTeam"] == team:
                wins += 1
            else:
                raise Exception("Tie game")

            opp_info = get_team_overall_rwp(opp_team, season)
            opp_round_wins += opp_info[0]
            opp_round_losses += opp_info[1]

        rwp = str(round(round_wins / (round_wins + round_losses), 2))
        oarwp = str(round(opp_round_wins / (opp_round_wins + opp_round_losses), 2))

        if len(rwp) == 3:
            rwp = rwp + "0"

        if len(oarwp) == 3:
            oarwp = oarwp + "0"

        map = map + ":"
        for i in range(15 - len(map)):
            map = map + " "

        info = map + "\t" + str(wins) + "-" + str(losses) + "\t" + rwp + "\t" + oarwp
        team_win_info.append(info)

    return team_win_info


def get_team_overall_rwp(team: str, season: int):
    """
    Gets round wins and losses for a team for demos in a folder

    :param season: CSC Season num
    :param team: Name of team
    :return: List containing total round wins and total round losses for the given team in the demos file folder
    """

    client = GraphqlClient(endpoint="https://stats.csconfederation.com/graphql")

    query = """
        query MyQuery {
            findManyTeamStats(
                where: {name: {equals: %s}, AND: {match: {season: {equals: %s}}}}
            ) {
                score
                ctR
                TR
            }
        }
    """ % ("\"" + team + "\"", season)

    data = client.execute(query=query)["data"]["findManyTeamStats"]

    wins = 0
    rounds = 0

    for match in data:
        wins += match["score"]
        rounds += match["ctR"] + match["TR"]

    losses = rounds - wins

    return [wins, losses]


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

    for player in data:
        if "SIGNED" in player["type"]:
            active_players.append(player["name"])

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

    info_message = "Player Map Stats:\n```               "
    players_message = ""

    for player in player_stats.keys():
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

    info_message = info_message + "\n" + players_message + "```"

    return info_message


def get_team_players_awp_stats(team: str, season: int):
    """
    Queries core and stats APIs to get overall awp stats for currently rostered players on the given team

    :param team: Team name
    :param season: CSC Season
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

    for player in data:
        if "SIGNED" in player["type"]:
            active_players.append(player["name"])

    client = GraphqlClient(endpoint="https://stats.csconfederation.com/graphql")

    names = ""
    awpr = ""

    for player in active_players:
        query = """
        query MyQuery {
            playerSeasonStats(name: "%s", season: %s, matchType: "Regulation") {
                awpR
            }
        }""" % (player, season)

        data = client.execute(query=query)

        names = names + player + (12 - len(player)) * " "

        awprstr = str(round(data["data"]["playerSeasonStats"]["awpR"], 2))
        awpr = awpr + awprstr + (12 - len(awprstr)) * " "

    return "Awp Kills / Round: \n```" + names + "\n" + awpr + "```"


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
            win_loss_stats[match["teamStats"][0]["name"]] = {"wins": 0, "losses": 0, "round_wins": 0, "round_losses": 0}

        win_loss_stats[match["teamStats"][0]["name"]]["round_wins"] += match["teamStats"][0]["score"]
        win_loss_stats[match["teamStats"][0]["name"]]["round_losses"] += match["teamStats"][1]["score"]

        if match["teamStats"][0]["score"] > match["teamStats"][1]["score"]:
            win_loss_stats[match["teamStats"][0]["name"]]["wins"] += 1
        else:
            win_loss_stats[match["teamStats"][0]["name"]]["losses"] += 1

        # Handle the second team
        if match["teamStats"][1]["name"] not in win_loss_stats.keys():
            win_loss_stats[match["teamStats"][1]["name"]] = {"wins": 0, "losses": 0, "round_wins": 0, "round_losses": 0}

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

    title = "**" + team + " (" + str(win_loss_stats[team]["wins"]) + "-" + str(win_loss_stats[team]["losses"]) + ", "
    title += str(round(win_loss_stats[team]["round_wins"] / (win_loss_stats[team]["round_wins"] +
                                                             win_loss_stats[team]["round_losses"]), 2)) + " RWP)**"

    title += "\nTeam Map Stats: \n"

    message = title + "```          Wins      Losses    RWP       Avg Opp Rwp\n"

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

    message += "```"

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

    ban_stats = {"de_inferno": [], "de_anubis": [], "de_ancient": [], "de_nuke": [],
                 "de_overpass": [], "de_mirage": [], "de_vertigo": []}

    for match in matches:
        if match["lobby"] is None or match["lobby"]["mapBans"] == []:
            continue

        for ban in match["lobby"]["mapBans"]:
            if ban["team"]["name"] == team:
                ban_stats[ban["map"]].append((ban["number"] + 1) // 2)

    message = "Map Ban Stats:\n```          # Banned  Avg Ban Round\n"

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

    message += "```"

    return message


def get_team_summary_stats(team: str, season: int, tier: str):
    message = get_team_opponent_stats(team, season, tier)
    message += get_team_map_bans(team, season)
    message += get_team_players_map_stats(team, season)
    message += get_team_players_awp_stats(team, season)

    return message


def send_discord_message(team: str, webhook_url: str, file_path: str, season: int):
    """
    Send a discord message with the scouting report PDF, and team map stats for a given team for demos from a given
    folder

    :param team: Name of team
    :param webhook_url: URL of webhook to send discord messages to
    :param file_path: File path to folder with demos
    :return: Nothing
    """
    get_scouting_report(team, file_path)

    win_info = get_team_map_win_info(team, file_path, season)

    info_message = team + " Scouting Report:```\n"
    info_message = info_message + "Map\t\t\t\tW-L\tRWP \tOARWP\n"

    for m in win_info:
        info_message = info_message + m + "\n"
    info_message = info_message + "```"

    info_message = info_message + get_team_players_map_stats(team, season) + get_team_players_awp_stats(team, season)

    webhook = DiscordWebhook(url=webhook_url, content=info_message)

    with open("./output/" + team + "_scouting.pdf", "rb") as f:
        webhook.add_file(file=f.read(), filename=team + ".pdf")

    webhook.execute()


# teams_and_webhooks: {"team1": "webhook1", "team2": "webhook2", ...}
def send_many_discord_messages(teams_and_webhooks: dict, file_path: str, season: int):
    """
    Sends discord message with scouting info for multiple teams

    :param season: CSC Season num
    :param teams_and_webhooks: Dictionary containing the team names as keys and webhooks to send the messages to as
    values
    :param file_path: File path to folder with demos
    :return: Nothing
    """
    for t, w in teams_and_webhooks.items():
        send_discord_message(t, w, file_path, season)


if __name__ == "__main__":
    team_name = "Angus Aimers"
    season_num = 13
    tier_name = "Challenger"

    print(get_team_summary_stats(team_name, season_num, tier_name))
