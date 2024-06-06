from demoparser2 import DemoParser
import os
import imageio.v3 as imageio
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib import pylab

import boto3
from botocore import UNSIGNED
from botocore.client import Config

import zipfile
import io

import jinja2
import datetime
import pathlib
import pdfkit
import pypdf


f = open("map_data.json")
MAP_DATA = json.load(f)
f.close()


# FROM AWPY VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV
def plot_map(
    map_name: str = "de_dust2", map_type: str = "original", *, dark: bool = False
) -> tuple[Figure, Axes]:
    """Plots a blank map.

    Args:
        map_name (str, optional): Map to search. Defaults to "de_dust2"
        map_type (str, optional): "original" or "simpleradar". Defaults to "original"
        dark (bool, optional): Only for use with map_type="simpleradar".
            Indicates if you want to use the SimpleRadar dark map type
            Defaults to False

    Returns:
        matplotlib fig and ax
    """
    base_path = os.path.join(os.path.dirname(__file__), f"""Map Images/{map_name}""")
    if map_type == "original":
        map_bg = imageio.imread(f"{base_path}.png")
        if map_name in MAP_DATA and "z_cutoff" in MAP_DATA[map_name]:
            map_bg_lower = imageio.imread(f"{base_path}_lower.png")
            map_bg = np.concatenate([map_bg, map_bg_lower])
    else:
        try:
            col = "dark" if dark else "light"
            map_bg = imageio.imread(f"{base_path}_{col}.png")
            if map_name in MAP_DATA and "z_cutoff" in MAP_DATA[map_name]:
                map_bg_lower = imageio.imread(f"{base_path}_lower_{col}.png")
                map_bg = np.concatenate([map_bg, map_bg_lower])
        except FileNotFoundError:
            map_bg = imageio.imread(f"{base_path}.png")
            if map_name in MAP_DATA and "z_cutoff" in MAP_DATA[map_name]:
                map_bg_lower = imageio.imread(f"{base_path}_lower.png")
                map_bg = np.concatenate([map_bg, map_bg_lower])
    figure, axes = plt.subplots()
    axes.set_facecolor('black')
    axes.imshow(map_bg, zorder=0)
    return figure, axes


def position_transform_all(
    map_name: str, position: tuple[float, float, float]
) -> tuple[float, float, float]:
    """Transforms an X or Y coordinate.

    Args:
        map_name (str): Map to search
        position (tuple): (X,Y,Z) coordinates

    Returns:
        tuple
    """
    current_map_data = MAP_DATA[map_name]
    start_x = current_map_data["pos_x"]
    start_y = current_map_data["pos_y"]
    scale = current_map_data["scale"]
    x = position[0] - start_x
    x /= scale
    y = start_y - position[1]
    y /= scale
    z = position[2]
    if "z_cutoff" in current_map_data and z < current_map_data["z_cutoff"]:
        y += 1024
    return (x, y, z)
# FROM AWPY ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


def get_map_tick_data(team_name: str):
    team = team_name.replace(" ", "")

    session = boto3.session.Session()
    client = session.client(
        's3',
        region_name='nyc3',
        endpoint_url='https://nyc3.digitaloceanspaces.com',
        config=Config(signature_version=UNSIGNED)
    )

    # Get a list of all the relevant demos
    response = client.list_objects(Bucket='cscdemos', Prefix='s13/', Delimiter='/')

    files = []

    for prefix in response["CommonPrefixes"]:
        if "Combine" not in prefix["Prefix"] and "P" not in prefix["Prefix"]:

            response = client.list_objects(Bucket='cscdemos', Prefix=prefix["Prefix"])

            for file in response["Contents"]:
                if team in file["Key"]:
                    files.append(file["Key"])

    position_info = {}

    # Iterate over all relevant demos found
    for i in range(len(files)):
        # Download the demo
        demo = client.get_object(Bucket='cscdemos', Key=files[i])["Body"].read()

        # Unzip the demo and write it to the temp file
        zip_file = zipfile.ZipFile(io.BytesIO(demo))

        filename = "tempdemo.dem"

        zipped = zipfile.ZipFile(io.BytesIO(demo))
        output = open(filename, "wb")

        for list_file in range(len(zipped.filelist)):
            if len(zipped.filelist) > 1 and list_file == 0:
                continue

            f = zipped.open(zipped.filelist[list_file])
            output.write(f.read())

            parser = DemoParser(filename)

            header = parser.parse_header()
            map_name = header["map_name"]
            tick_rate = 64

            freeze_time_end_ticks = parser.parse_event("round_freeze_end")["tick"].tolist()

            freeze_time_end_data = parser.parse_ticks(["current_equip_value", "team_name", "team_clan_name"], ticks=freeze_time_end_ticks)
            freeze_time_end_data = freeze_time_end_data[freeze_time_end_data["team_clan_name"] == team_name]

            buy_types = {"TERRORIST": {}, "CT": {}}

            for tick in freeze_time_end_ticks:
                buy_types["TERRORIST"][tick] = 0
                buy_types["CT"][tick] = 0

            for _, row in freeze_time_end_data.iterrows():
                buy_types[row["team_name"]][row["tick"]] += row["current_equip_value"]

            for i in range(len(freeze_time_end_ticks)):
                freeze_time_end_ticks[i] += tick_rate * 12

            tick_data = parser.parse_ticks(["X", "Y", "Z", "team_clan_name", "team_name"], ticks=freeze_time_end_ticks)
            tick_data = tick_data[tick_data["team_clan_name"] == team_name]

            positions = {
                "TERRORIST": {
                    "Pistol": {},
                    "Full Eco": {},
                    "Semi Eco": {},
                    "Semi Buy": {},
                    "Full Buy": {},
                },
                "CT": {
                    "Pistol": {},
                    "Full Eco": {},
                    "Semi Eco": {},
                    "Semi Buy": {},
                    "Full Buy": {},
                },
            }

            for _, row in tick_data.iterrows():
                tick = row["tick"]

                if freeze_time_end_ticks.index(tick) in [0, 12]:
                    if row["name"] not in positions[row["team_name"]]["Pistol"].keys():
                        positions[row["team_name"]]["Pistol"][row["name"]] = []

                    positions[row["team_name"]]["Pistol"][row["name"]].append({"x": row["X"], "y": row["Y"], "z": row["Z"]})
                    continue

                buy_type = ""

                if buy_types[row["team_name"]][row["tick"] - 12 * tick_rate] < 5000:
                    buy_type = "Full Eco"
                elif buy_types[row["team_name"]][row["tick"] - 12 * tick_rate] < 10000:
                    buy_type = "Semi Eco"
                elif buy_types[row["team_name"]][row["tick"] - 12 * tick_rate] < 20000:
                    buy_type = "Semi Buy"
                else:
                    buy_type = "Full Buy"

                if row["name"] not in positions[row["team_name"]][buy_type].keys():
                    positions[row["team_name"]][buy_type][row["name"]] = []

                positions[row["team_name"]][buy_type][row["name"]].append({"x": row["X"], "y": row["Y"], "z": row["Z"]})

            if map_name not in position_info.keys():
                position_info[map_name] = positions
            else:
                for side in positions.keys():
                    for buy in positions[side].keys():
                        for player in positions[side][buy].keys():
                            if player not in position_info[map_name][side][buy].keys():
                                position_info[map_name][side][buy][player] = positions[side][buy][player]
                            else:
                                position_info[map_name][side][buy][player] += positions[side][buy][player]

    return position_info

# map_position_info: {"t": {"Pistol": player_positions, "Full Eco": {}, "Semi Eco": {}, ...}, "ct": {}}
def get_map_buy_pictures(
        map_name: str, map_position_info: dict, players
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
                players,
            )

            plt.savefig(
                "./temp-images/" + side + "_" + buy + ".png",
                bbox_inches="tight",
                dpi=300,
            )

            if side == "CT" and buy == "Full Buy":
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
        map_name: str, player_positions: dict, players: list
):
    """
    Creates and saves a plot with player positions and grenade trajectories

    :param map_name: Name of map
    :param player_positions: Dictionary with a list of positions for each player
    # :param grenades: Dictionary with a list of grenades thrown for each player
    :param players: List of players plotted so far. Used to keep colors on plots for players consistent
    :return: The figure and axes for the plot, and an updated list of plotted players
    """
    figure, axes = plot_map(map_name=map_name)

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

    # for player in grenades.keys():
    #     if player not in players:
    #         players.append(player)
    #     for grenade in grenades[player]:
    #         if grenade["type"] == "Decoy Grenade":
    #             continue
    #
    #         if map_name not in ("de_vertigo", "de_nuke"):
    #             x1, y1, z1 = position_transform_all(
    #                 map_name, (grenade["X1"], grenade["Y1"], grenade["Z1"])
    #             )
    #             x2, y2, z2 = position_transform_all(
    #                 map_name, (grenade["X2"], grenade["Y2"], grenade["Z2"])
    #             )
    #         elif map_name == "de_vertigo":
    #             # Don't plot a grenade that went off the map
    #             if grenade["Z2"] < 10000:
    #                 continue
    #
    #             x1, y1, z1 = position_transform_all(
    #                 map_name, (grenade["X1"], grenade["Y1"], grenade["Z2"])
    #             )
    #             x2, y2, z2 = position_transform_all(
    #                 map_name, (grenade["X2"], grenade["Y2"], grenade["Z2"])
    #             )
    #         else:
    #             x1, y1, z1 = position_transform_all(
    #                 map_name, (grenade["X1"], grenade["Y1"], grenade["Z2"])
    #             )
    #             x2, y2, z2 = position_transform_all(
    #                 map_name, (grenade["X2"], grenade["Y2"], grenade["Z2"])
    #             )
    #
    #         # From awpy.visualization.plot.plot_nades()
    #         g_color = {
    #             "Incendiary Grenade": "red",
    #             "Molotov": "red",
    #             "Smoke Grenade": "gray",
    #             "HE Grenade": "green",
    #             "Flashbang": "gold",
    #         }[grenade["type"]]
    #
    #         axes.plot(
    #             [x1, x2], [y1, y2], color=("C" + str(players.index(player))), alpha=0.1
    #         )
    #         axes.scatter(x2, y2, color=g_color, s=dot_size, alpha=0.6, marker="x")

    for player in player_positions.keys():
        if player not in players:
            players.append(player)
        for position in player_positions[player]:
            x, y, z = position_transform_all(
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


def get_all_demos_tick_data(season: int, team: str):
    team = team.replace(" ", "")

    session = boto3.session.Session()
    client = session.client(
        's3',
        region_name='nyc3',
        endpoint_url='https://nyc3.digitaloceanspaces.com',
        config=Config(signature_version=UNSIGNED)
    )

    # Get a list of all the relevant demos
    response = client.list_objects(Bucket='cscdemos', Prefix='s13/', Delimiter='/')

    files = []

    for prefix in response["CommonPrefixes"]:
        if "Combine" not in prefix["Prefix"] and "P" not in prefix["Prefix"]:

            response = client.list_objects(Bucket='cscdemos', Prefix=prefix["Prefix"])

            for file in response["Contents"]:
                if team in file["Key"]:
                    files.append(file["Key"])

    demo = client.get_object(Bucket='cscdemos', Key=files[0])["Body"].read()

    zip_file = zipfile.ZipFile(io.BytesIO(demo))

    filename = "tempdemo.dem"

    with (
        zipfile.ZipFile(io.BytesIO(demo)) as zipped,
        open(filename, "wb") as output,
    ):
        with zipped.open(zipped.filelist[0]) as f:
            output.write(f.read())


def plot_tick_data(tick_data, map_name):
    total_dots = 0

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

    fig, axes = plot_map(map_name=map_name)

    unique_players = []

    for _, row in tick_data.iterrows():
        x, y, z = position_transform_all(
            map_name, (row["X"], row["Y"], row["Z"])
        )

        if row["name"] not in unique_players:
            unique_players.append(row["name"])

        axes.scatter(
            x,
            y,
            color=("C" + str(unique_players.index(row["name"]))),
            label=row["name"],
            s=dot_size,
            zorder=100,
        )

    plt.show()


if __name__ == "__main__":
    team = "The Watchers"

    position_info = get_map_tick_data(team)

    merger = pypdf.PdfMerger()

    path = str(pathlib.Path(__file__).parent.resolve())

    images = {
        "t_Pistol": path + "/temp-images/TERRORIST_Pistol.png",
        "t_FullEco": path + "/temp-images/TERRORIST_Full Eco.png",
        "t_SemiEco": path + "/temp-images/TERRORIST_Semi Eco.png",
        "t_SemiBuy": path + "/temp-images/TERRORIST_Semi Buy.png",
        "t_FullBuy": path + "/temp-images/TERRORIST_Full Buy.png",
        "ct_Pistol": path + "/temp-images/CT_Pistol.png",
        "ct_FullEco": path + "/temp-images/CT_Full Eco.png",
        "ct_SemiEco": path + "/temp-images/CT_Semi Eco.png",
        "ct_SemiBuy": path + "/temp-images/CT_Semi Buy.png",
        "ct_FullBuy": path + "/temp-images/CT_Full Buy.png",
    }

    players = []

    for m in position_info.keys():
        players = get_map_buy_pictures(m, position_info[m], players)

        to_pdf(team, m, "Opponents go here", images, "./temp-pdfs/" + m + ".pdf")

        merger.append("./temp-pdfs/" + m + ".pdf")

    merger.write("output/Scouting.pdf")
    merger.close()

