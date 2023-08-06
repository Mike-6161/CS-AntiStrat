from awpy.parser import DemoParser
from awpy.visualization import plot
import datetime
import pdfkit
import jinja2
import os
import json
from matplotlib import pyplot as plt
from matplotlib import pylab
import pypdf
import pathlib
from discord_webhook import DiscordWebhook


def get_team_demo_file_paths(team: str, folder: str, use_file_names: bool):
    file_paths = []
    if use_file_names:
        for file in os.listdir(folder):
            if file[(len(file) - 3):len(file)] == "dem" and team.replace(" ", "") in file:
                file_paths.append(folder + '/' + file)

    return file_paths


def parse_and_sort_by_map(files: list, file_folder: str):
    maps = {}
    for file in files:
        # if demo is already parsed
        print(file[0:(len(file) - 3)] + "json")
        if os.path.isfile(file[0:(len(file) - 3)] + "json"):
            f = open((file[0:(len(file) - 3)] + "json"))
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
                outpath=file_folder
            )

            data = demo_parser.parse(clean=True)

        if data["mapName"] in maps.keys():
            maps[data["mapName"]].append(file[0:(len(file) - 3)] + "json")
        else:
            maps[data["mapName"]] = [file[0:(len(file) - 3)] + "json"]

    return maps


def get_scouting_info(team: str, map_files: dict):
    position_info = {}
    grenades_info = {}
    opponents = {}
    for map_name in map_files.keys():
        map_opponents = []
        positions = {"t": {"Pistol": {}, "Full Eco": {}, "Semi Eco": {}, "Semi Buy": {}, "Full Buy": {}},
                     "ct": {"Pistol": {}, "Full Eco": {}, "Semi Eco": {}, "Semi Buy": {}, "Full Buy": {}}}
        grenades = {"t": {"Pistol": {}, "Full Eco": {}, "Semi Eco": {}, "Semi Buy": {}, "Full Buy": {}},
                    "ct": {"Pistol": {}, "Full Eco": {}, "Semi Eco": {}, "Semi Buy": {}, "Full Buy": {}}}

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

                            positions[side][buy][p["name"]].append({"x": p["x"], "y": p["y"], "z": p["z"]})

                        break

                for g in r["grenades"]:
                    if g["throwSeconds"] <= 12 and g["throwerSide"] == side.upper():
                        if g["throwerName"] not in grenades[side][buy].keys():
                            grenades[side][buy][g["throwerName"]] = []

                        grenades[side][buy][g["throwerName"]].append({"type": g["grenadeType"],
                                                                      "X1": g["throwerX"], "Y1": g["throwerY"],
                                                                      "Z1": g["throwerZ"], "X2": g["grenadeX"],
                                                                      "Y2": g["grenadeY"], "Z2": g["grenadeZ"]})

        position_info[map_name] = positions
        grenades_info[map_name] = grenades
        opponents[map_name] = map_opponents

    return opponents, position_info, grenades_info


# map_position_info: {"t": {"Pistol": player_positions, "Full Eco": {}, "Semi Eco": {}, ...}, "ct": {}}
def get_map_buy_pictures(map_name: str, map_position_info: dict, grenades_info: dict, players):
    for side in map_position_info.keys():
        for buy in map_position_info[side].keys():
            figure, axes, players = get_single_plot(map_name, map_position_info[side][buy],
                                                    grenades_info[side][buy], players)

            plt.savefig("./temp-images/" + side + "_" + buy + ".png", bbox_inches='tight', dpi=300)

            if side == "ct" and buy == "Full Buy":
                handles, labels = plt.gca().get_legend_handles_labels()
                by_label = dict(zip(labels, handles))
                fig_legend = pylab.figure(figsize=(1.5, 1.3))
                fig_legend.legend(by_label.values(), by_label.keys())
                #pylab.figlegend(*axes.get_legend_handles_labels())

                fig_legend.savefig("./temp-images/legend.png", bbox_inches='tight', dpi=300)
                plt.close()

            plt.close()

    return players


# player positions: {player1: [{"x": 0, "y": 0, "z": 0}, ...], player2: [], ...}
def get_single_plot(map_name: str, player_positions: dict, grenades: dict, players: list):
    figure, axes = plot.plot_map(map_name=map_name, dark=False)

    total_dots = 0

    for key in player_positions.keys():
        total_dots += len(player_positions[key])

    if map_name in ("de_vertigo", "de_nuke"):
        if total_dots > 50:
            dot_size = 15
        else:
            dot_size = 15
    else:
        if total_dots > 50:
            dot_size = 60
        else:
            dot_size = 60

    for player in grenades.keys():
        if player not in players:
            players.append(player)
        for grenade in grenades[player]:
            if grenade["type"] == "Decoy Grenade":
                continue

            x1, y1, z1 = plot.position_transform_all(map_name, [grenade["X1"], grenade["Y1"], grenade["Z1"]])
            x2, y2, z2 = plot.position_transform_all(map_name, [grenade["X2"], grenade["Y2"], grenade["Z2"]])

            # From awpy.visualization.plot.plot_nades()
            g_color = {
                "Incendiary Grenade": "red",
                "Molotov": "red",
                "Smoke Grenade": "gray",
                "HE Grenade": "green",
                "Flashbang": "gold"
            }[grenade["type"]]

            axes.plot([x1, x2], [y1, y2], color=("C" + str(players.index(player))), alpha=0.1)
            axes.scatter(x2, y2, color=g_color, s=dot_size, alpha=0.6, marker="x")

    for player in player_positions.keys():
        if player not in players:
            players.append(player)
        for position in player_positions[player]:
            x, y, z = plot.position_transform_all(map_name, [position["x"], position["y"], position["z"]])

            axes.scatter(x, y, color=("C" + str(players.index(player))), label=player, s=dot_size, zorder=100)

    axes.get_xaxis().set_visible(b=False)
    axes.get_yaxis().set_visible(b=False)

    figure.set_size_inches(10, 10)

    return figure, axes, players


def to_pdf(team: str, map_name: str, opponents: list, images: dict, output_file: str):
    template_loader = jinja2.FileSystemLoader('./')
    template_env = jinja2.Environment(loader=template_loader)

    path = str(pathlib.Path(__file__).parent.resolve())

    context = {"Team": team, "Map": map_name, "Opponents": opponents, "Date": datetime.datetime.now().date,
               "Legend": (path + "/temp-images/legend.png")} | images

    template = template_env.get_template('map-template.html')
    output_text = template.render(context)

    if map_name in ("de_vertigo", "de_nuke"):
        page_height = 400
    else:
        page_height = 270

    config = pdfkit.configuration(wkhtmltopdf="C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe")
    pdfkit.from_string(output_text, output_file, configuration=config, options={"enable-local-file-access": "",
                                                                                "page-height": page_height,
                                                                                "page-width": 400},
                       css="map-template.css")


def get_scouting_report(team: str, file_path: str):
    demo_files = get_team_demo_file_paths(team, file_path, True)
    sorted_json_files = parse_and_sort_by_map(demo_files, file_path)
    opponents, position_info, grenades_info = get_scouting_info(team, sorted_json_files)

    path = str(pathlib.Path(__file__).parent.resolve())

    images = {"t_Pistol": path + "/temp-images/t_Pistol.png", "t_FullEco": path + "/temp-images/t_Full Eco.png",
              "t_SemiEco": path + "/temp-images/t_Semi Eco.png", "t_SemiBuy": path + "/temp-images/t_Semi Buy.png",
              "t_FullBuy": path + "/temp-images/t_Full Buy.png", "ct_Pistol": path + "/temp-images/ct_Pistol.png",
              "ct_FullEco": path + "/temp-images/ct_Full Eco.png", "ct_SemiEco": path + "/temp-images/ct_Semi Eco.png",
              "ct_SemiBuy": path + "/temp-images/ct_Semi Buy.png", "ct_FullBuy": path + "/temp-images/ct_Full Buy.png"}

    merger = pypdf.PdfMerger()

    players = []

    for m in opponents.keys():
        players = get_map_buy_pictures(m, position_info[m], grenades_info[m], players)

        opps = 'Opponents: ' + ', '.join([str(elem) for elem in opponents[m]])

        to_pdf(team, m, opps, images, "./temp-pdfs/" + m + ".pdf")

        merger.append("./temp-pdfs/" + m + ".pdf")

    merger.write("output/" + team + "_scouting.pdf")
    merger.close()


def get_team_map_win_info(team: str, file_path: str):
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

            opp_info = get_team_overall_rwp(opp_team, file_path)
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


def get_team_overall_rwp(team: str, file_path: str):
    demo_files = get_team_demo_file_paths(team, file_path, True)
    sorted_json_files = parse_and_sort_by_map(demo_files, file_path)

    round_wins = 0
    round_losses = 0

    for map in sorted_json_files.keys():
        for match in sorted_json_files[map]:
            file = open(match)
            data = json.load(file)
            file.close()
            for r in data["gameRounds"]:
                if r["winningTeam"] == team:
                    round_wins += 1
                else:
                    round_losses += 1

    return [round_wins, round_losses]


def send_discord_message(team: str, webhook_url: str, file_path: str):
    get_scouting_report(team, file_path)

    win_info = get_team_map_win_info(team, file_path)

    info_message = team + " Scouting Report:```\n"
    info_message = info_message + "Map\t\t\t\tW-L\tRWP \tOARWP\n"

    for m in win_info:
        info_message = info_message + m + "\n"
    info_message = info_message + "```"

    webhook = DiscordWebhook(url=webhook_url, content=info_message)

    with open("./output/" + team + "_scouting.pdf", "rb") as f:
        webhook.add_file(file=f.read(), filename=team + ".pdf")

    webhook.execute()


# teams_and_webhooks: {"team1": "webhook1", "team2": "webhook2", ...}
def send_many_discord_messages(teams_and_webhooks: dict, file_path: str):
    for t, w in teams_and_webhooks.items():
        send_discord_message(t, w, file_path)
