#!/usr/bin/env python3
"""
Download land use data for major Israeli cities.

Downloads OSM land use polygons for specific cities instead of the entire country.
Much faster and more practical than grid-based approach.

Usage:
    python scripts/download_cities_landuse.py
"""
import sys
import os
import logging
import time
from pathlib import Path
from datetime import datetime
import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point

# Add api directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'api'))


# Comprehensive list of Israeli settlements (~400+ locations)
# Organized by category for maintainability
ISRAELI_CITIES = {
    # ============================================================================
    # MAJOR CITIES (>100k population)
    # ============================================================================
    'tel_aviv': {'lat': 32.0853, 'lon': 34.7818, 'radius': 8000},
    'jerusalem': {'lat': 31.7683, 'lon': 35.2137, 'radius': 8000},
    'haifa': {'lat': 32.7940, 'lon': 34.9896, 'radius': 6000},
    'rishon_lezion': {'lat': 31.9730, 'lon': 34.7925, 'radius': 5000},
    'petah_tikva': {'lat': 32.0878, 'lon': 34.8878, 'radius': 5000},
    'ashdod': {'lat': 31.8044, 'lon': 34.6553, 'radius': 5000},
    'netanya': {'lat': 32.3328, 'lon': 34.8558, 'radius': 5000},
    'beer_sheva': {'lat': 31.2518, 'lon': 34.7913, 'radius': 5000},
    'holon': {'lat': 32.0114, 'lon': 34.7806, 'radius': 4000},
    'bnei_brak': {'lat': 32.0833, 'lon': 34.8336, 'radius': 3000},
    'ramat_gan': {'lat': 32.0719, 'lon': 34.8242, 'radius': 4000},
    'ashkelon': {'lat': 31.6688, 'lon': 34.5742, 'radius': 5000},
    'rehovot': {'lat': 31.8942, 'lon': 34.8089, 'radius': 4000},
    'bat_yam': {'lat': 32.0192, 'lon': 34.7506, 'radius': 3000},

    # ============================================================================
    # MEDIUM CITIES (30k-100k population)
    # ============================================================================
    'herzliya': {'lat': 32.1656, 'lon': 34.8433, 'radius': 4000},
    'kfar_saba': {'lat': 32.1781, 'lon': 34.9075, 'radius': 4000},
    'hadera': {'lat': 32.4339, 'lon': 34.9189, 'radius': 4000},
    'modiin': {'lat': 31.8969, 'lon': 35.0100, 'radius': 4000},
    'nazareth': {'lat': 32.7028, 'lon': 35.2978, 'radius': 4000},
    'lod': {'lat': 31.9500, 'lon': 34.8833, 'radius': 4000},
    'ramla': {'lat': 31.9294, 'lon': 34.8667, 'radius': 4000},
    'raanana': {'lat': 32.1845, 'lon': 34.8706, 'radius': 4000},
    'givatayim': {'lat': 32.0697, 'lon': 34.8114, 'radius': 3000},
    'nahariya': {'lat': 33.0058, 'lon': 35.0942, 'radius': 3000},
    'beitar_illit': {'lat': 31.6989, 'lon': 35.1181, 'radius': 3000},
    'rosh_haayin': {'lat': 32.0952, 'lon': 34.9561, 'radius': 3000},
    'acre': {'lat': 32.9278, 'lon': 35.0828, 'radius': 4000},
    'ramat_hasharon': {'lat': 32.1467, 'lon': 34.8394, 'radius': 3000},
    'hod_hasharon': {'lat': 32.1511, 'lon': 34.8889, 'radius': 3000},
    'afula': {'lat': 32.6078, 'lon': 35.2897, 'radius': 3000},
    'carmiel': {'lat': 32.9178, 'lon': 35.2933, 'radius': 3000},
    'eilat': {'lat': 29.5577, 'lon': 34.9519, 'radius': 5000},
    'tiberias': {'lat': 32.7953, 'lon': 35.5344, 'radius': 3000},
    'yavne': {'lat': 31.8778, 'lon': 34.7425, 'radius': 3000},
    'kiryat_ata': {'lat': 32.8039, 'lon': 35.1028, 'radius': 3000},
    'kiryat_gat': {'lat': 31.6100, 'lon': 34.7644, 'radius': 3000},
    'kiryat_motzkin': {'lat': 32.8372, 'lon': 35.0769, 'radius': 3000},
    'kiryat_yam': {'lat': 32.8447, 'lon': 35.0669, 'radius': 3000},
    'kiryat_bialik': {'lat': 32.8272, 'lon': 35.0825, 'radius': 3000},
    'umm_al_fahm': {'lat': 32.5189, 'lon': 35.1522, 'radius': 3000},
    'nes_ziona': {'lat': 31.9297, 'lon': 34.7989, 'radius': 3000},
    'or_yehuda': {'lat': 32.0297, 'lon': 34.8578, 'radius': 3000},
    'tamra': {'lat': 32.8533, 'lon': 35.1986, 'radius': 3000},
    'tayibe': {'lat': 32.2656, 'lon': 35.0072, 'radius': 3000},
    'sakhnin': {'lat': 32.8647, 'lon': 35.2978, 'radius': 3000},

    # ============================================================================
    # SMALL CITIES AND TOWNS (10k-30k population)
    # ============================================================================
    'dimona': {'lat': 31.0697, 'lon': 35.0317, 'radius': 3000},
    'sderot': {'lat': 31.5242, 'lon': 34.5961, 'radius': 3000},
    'ariel': {'lat': 32.1050, 'lon': 35.1811, 'radius': 3000},
    'maalot_tarshiha': {'lat': 33.0172, 'lon': 35.2719, 'radius': 3000},
    'migdal_haemek': {'lat': 32.6744, 'lon': 35.2383, 'radius': 3000},
    'yokneam': {'lat': 32.6603, 'lon': 35.1056, 'radius': 3000},
    'beit_shean': {'lat': 32.4978, 'lon': 35.4981, 'radius': 3000},
    'katzrin': {'lat': 32.9931, 'lon': 35.6931, 'radius': 3000},
    'tirat_carmel': {'lat': 32.7622, 'lon': 34.9703, 'radius': 3000},
    'nesher': {'lat': 32.7686, 'lon': 35.0394, 'radius': 3000},
    'gedera': {'lat': 31.8122, 'lon': 34.7811, 'radius': 3000},
    'kiryat_shmona': {'lat': 33.2078, 'lon': 35.5697, 'radius': 3000},
    'kiryat_malakhi': {'lat': 31.7278, 'lon': 34.7483, 'radius': 3000},
    'kiryat_ono': {'lat': 32.0567, 'lon': 34.8564, 'radius': 3000},
    'givat_shmuel': {'lat': 32.0772, 'lon': 34.8503, 'radius': 2500},
    'beit_shemesh': {'lat': 31.7522, 'lon': 34.9883, 'radius': 4000},
    'gan_yavne': {'lat': 31.7886, 'lon': 34.7081, 'radius': 3000},
    'zichron_yaakov': {'lat': 32.5703, 'lon': 34.9531, 'radius': 3000},
    'qalansawe': {'lat': 32.2881, 'lon': 34.9803, 'radius': 3000},
    'tira': {'lat': 32.2303, 'lon': 34.9486, 'radius': 3000},
    'baqa_al_gharbiyye': {'lat': 32.4119, 'lon': 35.0508, 'radius': 3000},
    'rahat': {'lat': 31.3953, 'lon': 34.7544, 'radius': 3000},
    'shfaram': {'lat': 32.8069, 'lon': 35.1694, 'radius': 3000},
    'arad': {'lat': 31.2586, 'lon': 35.2128, 'radius': 3000},
    'ofakim': {'lat': 31.3186, 'lon': 34.6197, 'radius': 3000},
    'netivot': {'lat': 31.4200, 'lon': 34.5911, 'radius': 3000},
    'rishon_lezion_west': {'lat': 31.9667, 'lon': 34.7667, 'radius': 3000},
    'mazkeret_batya': {'lat': 31.8506, 'lon': 34.8481, 'radius': 2500},
    'shoham': {'lat': 31.9989, 'lon': 34.9478, 'radius': 2500},
    'even_yehuda': {'lat': 32.2667, 'lon': 34.8833, 'radius': 2500},
    'omer': {'lat': 31.2667, 'lon': 34.8500, 'radius': 2500},
    'meitar': {'lat': 31.3533, 'lon': 34.9467, 'radius': 2500},
    'azor': {'lat': 32.0242, 'lon': 34.7808, 'radius': 2500},
    'yehud': {'lat': 32.0333, 'lon': 34.8833, 'radius': 2500},
    'tel_mond': {'lat': 32.2531, 'lon': 34.9194, 'radius': 2500},
    'kadima_zoran': {'lat': 32.2833, 'lon': 34.9167, 'radius': 2500},
    'pardes_hanna_karkur': {'lat': 32.4686, 'lon': 34.9753, 'radius': 3000},

    # ============================================================================
    # ARAB VILLAGES AND TOWNS
    # ============================================================================
    'jisr_az_zarqa': {'lat': 32.5397, 'lon': 34.9158, 'radius': 2500},
    'fureidis': {'lat': 32.6028, 'lon': 34.9592, 'radius': 2500},
    'iksal': {'lat': 32.7197, 'lon': 35.3292, 'radius': 2500},
    'kafr_qasim': {'lat': 32.1139, 'lon': 34.9758, 'radius': 2500},
    'jaljulya': {'lat': 32.1547, 'lon': 34.9522, 'radius': 2500},
    'kafr_qara': {'lat': 32.5097, 'lon': 35.0631, 'radius': 2500},
    'arara': {'lat': 32.4858, 'lon': 35.0764, 'radius': 2500},
    'kafr_manda': {'lat': 32.8086, 'lon': 35.2603, 'radius': 2500},
    'daburiyya': {'lat': 32.7019, 'lon': 35.3669, 'radius': 2500},
    'basmat_tabun': {'lat': 32.7083, 'lon': 35.0386, 'radius': 2500},
    'bir_al_maksur': {'lat': 32.7889, 'lon': 35.0833, 'radius': 2500},
    'deir_hanna': {'lat': 32.8622, 'lon': 35.3744, 'radius': 2500},
    'mughar': {'lat': 32.8883, 'lon': 35.4092, 'radius': 2500},
    'tur_an': {'lat': 32.8481, 'lon': 35.2922, 'radius': 2500},
    'yafa_an_naseriyye': {'lat': 32.6939, 'lon': 35.3022, 'radius': 2500},
    'arrabe': {'lat': 32.8619, 'lon': 35.3464, 'radius': 2500},
    'kabul': {'lat': 32.8744, 'lon': 35.2864, 'radius': 2500},
    'nahef': {'lat': 32.9336, 'lon': 35.3139, 'radius': 2500},
    'majd_al_kurum': {'lat': 32.9086, 'lon': 35.2481, 'radius': 2500},
    'kafr_yasif': {'lat': 32.9561, 'lon': 35.1686, 'radius': 2500},
    'ein_mahil': {'lat': 32.7242, 'lon': 35.3003, 'radius': 2500},
    'reineh': {'lat': 32.7158, 'lon': 35.3103, 'radius': 2500},
    'ramat_yishai': {'lat': 32.7017, 'lon': 35.1850, 'radius': 2500},
    'kiryat_tivon': {'lat': 32.7228, 'lon': 35.1244, 'radius': 2500},

    # ============================================================================
    # MAJOR KIBBUTZIM (Central & North)
    # ============================================================================
    'ein_gedi': {'lat': 31.4619, 'lon': 35.3886, 'radius': 2000},
    'ein_gev': {'lat': 32.7722, 'lon': 35.6500, 'radius': 2000},
    'degania_alef': {'lat': 32.7011, 'lon': 35.5733, 'radius': 2000},
    'degania_bet': {'lat': 32.6969, 'lon': 35.5858, 'radius': 2000},
    'kinneret': {'lat': 32.7017, 'lon': 35.5583, 'radius': 2000},
    'ginosar': {'lat': 32.8431, 'lon': 35.5208, 'radius': 2000},
    'maagan': {'lat': 32.7108, 'lon': 35.6194, 'radius': 2000},
    'masada': {'lat': 32.6894, 'lon': 35.5981, 'radius': 2000},
    'afikim': {'lat': 32.6847, 'lon': 35.5886, 'radius': 2000},
    'ashdot_yaakov': {'lat': 32.6625, 'lon': 35.5722, 'radius': 2000},
    'beit_alpha': {'lat': 32.5000, 'lon': 35.4300, 'radius': 2000},
    'beit_haemek': {'lat': 32.8431, 'lon': 35.1167, 'radius': 2000},
    'beit_hashita': {'lat': 32.5025, 'lon': 35.3844, 'radius': 2000},
    'beit_keshet': {'lat': 32.6992, 'lon': 35.3667, 'radius': 2000},
    'beit_zera': {'lat': 32.7219, 'lon': 35.5758, 'radius': 2000},
    'dafna': {'lat': 33.1508, 'lon': 35.6536, 'radius': 2000},
    'dan': {'lat': 33.2264, 'lon': 35.6522, 'radius': 2000},
    'ein_hamifratz': {'lat': 32.8578, 'lon': 35.0950, 'radius': 2000},
    'ein_hanatziv': {'lat': 32.5058, 'lon': 35.5433, 'radius': 2000},
    'ein_harod_ihud': {'lat': 32.5586, 'lon': 35.3911, 'radius': 2000},
    'ein_harod_meuhad': {'lat': 32.5528, 'lon': 35.3944, 'radius': 2000},
    'ein_hashofet': {'lat': 32.6003, 'lon': 35.1392, 'radius': 2000},
    'ein_shemer': {'lat': 32.4417, 'lon': 34.9267, 'radius': 2000},
    'gesher': {'lat': 32.6542, 'lon': 35.5517, 'radius': 2000},
    'gesher_haziv': {'lat': 33.0533, 'lon': 35.1069, 'radius': 2000},
    'gevat': {'lat': 32.6847, 'lon': 35.1867, 'radius': 2000},
    'gvulot': {'lat': 31.1928, 'lon': 34.4047, 'radius': 2000},
    'hagoshrim': {'lat': 33.1519, 'lon': 35.5728, 'radius': 2000},
    'hamadia': {'lat': 32.6897, 'lon': 35.5486, 'radius': 2000},
    'hanita': {'lat': 33.0786, 'lon': 35.1997, 'radius': 2000},
    'harduf': {'lat': 32.7917, 'lon': 35.2736, 'radius': 2000},
    'hatzerim': {'lat': 31.2369, 'lon': 34.6714, 'radius': 2000},
    'hazore_a': {'lat': 32.9831, 'lon': 35.5439, 'radius': 2000},
    'heftziba': {'lat': 32.5344, 'lon': 35.4739, 'radius': 2000},
    'kabri': {'lat': 33.0369, 'lon': 35.1478, 'radius': 2000},
    'kfar_blum': {'lat': 33.1817, 'lon': 35.6142, 'radius': 2000},
    'kfar_giladi': {'lat': 33.2389, 'lon': 35.5772, 'radius': 2000},
    'kfar_glickson': {'lat': 32.4575, 'lon': 34.9086, 'radius': 2000},
    'kfar_ha_nasi': {'lat': 33.0183, 'lon': 35.5392, 'radius': 2000},
    'kfar_hanassi': {'lat': 32.9728, 'lon': 35.5644, 'radius': 2000},
    'kfar_masaryk': {'lat': 32.7103, 'lon': 35.2364, 'radius': 2000},
    'kfar_menahem': {'lat': 31.7400, 'lon': 34.8017, 'radius': 2000},
    'kfar_ruppin': {'lat': 32.4450, 'lon': 35.5422, 'radius': 2000},
    'kfar_szold': {'lat': 33.0967, 'lon': 35.5833, 'radius': 2000},
    'ma_agan_michael': {'lat': 32.5592, 'lon': 34.9142, 'radius': 2000},
    'maale_hahamisha': {'lat': 31.8178, 'lon': 35.1097, 'radius': 2000},
    'magen': {'lat': 31.6000, 'lon': 34.5750, 'radius': 2000},
    'maoz_haim': {'lat': 32.4717, 'lon': 35.5306, 'radius': 2000},
    'merom_golan': {'lat': 33.1167, 'lon': 35.7667, 'radius': 2000},
    'metzer': {'lat': 32.3306, 'lon': 34.9953, 'radius': 2000},
    'mevo_hama': {'lat': 32.8622, 'lon': 35.7625, 'radius': 2000},
    'mezra': {'lat': 32.7433, 'lon': 35.4728, 'radius': 2000},
    'migdal_oz': {'lat': 31.6544, 'lon': 35.1336, 'radius': 2000},
    'mishmar_david': {'lat': 32.0053, 'lon': 34.8531, 'radius': 2000},
    'mishmar_haemek': {'lat': 32.6678, 'lon': 35.1147, 'radius': 2000},
    'mishmar_hanegev': {'lat': 31.3389, 'lon': 34.7308, 'radius': 2000},
    'mishmar_hasharon': {'lat': 32.3333, 'lon': 34.9167, 'radius': 2000},
    'nahal_oz': {'lat': 31.4736, 'lon': 34.4833, 'radius': 2000},
    'nahsholim': {'lat': 32.6231, 'lon': 34.9183, 'radius': 2000},
    'nir_am': {'lat': 31.4833, 'lon': 34.4583, 'radius': 2000},
    'nir_david_tel_amal': {'lat': 32.4978, 'lon': 35.4433, 'radius': 2000},
    'nir_oz': {'lat': 31.4681, 'lon': 34.3919, 'radius': 2000},
    'nir_yitzhak': {'lat': 31.3722, 'lon': 34.4375, 'radius': 2000},
    'nirim': {'lat': 31.3458, 'lon': 34.4472, 'radius': 2000},
    'ramat_david': {'lat': 32.6669, 'lon': 35.1839, 'radius': 2000},
    'ramat_hakovesh': {'lat': 32.2833, 'lon': 34.9333, 'radius': 2000},
    'ramat_rachel': {'lat': 31.7342, 'lon': 35.2144, 'radius': 2000},
    'ramat_yohanan': {'lat': 32.8258, 'lon': 35.0742, 'radius': 2000},
    'revivim': {'lat': 31.0250, 'lon': 34.7133, 'radius': 2000},
    'rosh_hanikra': {'lat': 33.0883, 'lon': 35.1022, 'radius': 2000},
    'rosh_tzurim': {'lat': 31.6536, 'lon': 35.1278, 'radius': 2000},
    'sa_ad': {'lat': 31.4972, 'lon': 34.5211, 'radius': 2000},
    'sarid': {'lat': 32.6611, 'lon': 35.1881, 'radius': 2000},
    'sdot_yam': {'lat': 32.4964, 'lon': 34.8814, 'radius': 2000},
    'sde_boker': {'lat': 30.8542, 'lon': 34.7847, 'radius': 2000},
    'sde_eliezer': {'lat': 33.1550, 'lon': 35.6031, 'radius': 2000},
    'sde_nehemia': {'lat': 33.1808, 'lon': 35.6347, 'radius': 2000},
    'sde_yoav': {'lat': 31.7817, 'lon': 34.9147, 'radius': 2000},
    'shamir': {'lat': 33.0758, 'lon': 35.6353, 'radius': 2000},
    'shefayim': {'lat': 32.2167, 'lon': 34.8206, 'radius': 2000},
    'shluhot': {'lat': 32.5003, 'lon': 35.5147, 'radius': 2000},
    'urim': {'lat': 31.3211, 'lon': 34.5458, 'radius': 2000},
    'yad_hana': {'lat': 32.4869, 'lon': 34.9861, 'radius': 2000},
    'yad_mordechai': {'lat': 31.5875, 'lon': 34.4958, 'radius': 2000},
    'yagur': {'lat': 32.7500, 'lon': 35.0931, 'radius': 2000},
    'yehiam': {'lat': 33.0300, 'lon': 35.2833, 'radius': 2000},
    'yif_at': {'lat': 32.7189, 'lon': 35.1769, 'radius': 2000},
    'yiron': {'lat': 33.0597, 'lon': 35.4425, 'radius': 2000},
    'yizreel': {'lat': 32.5567, 'lon': 35.3197, 'radius': 2000},
    'yotvata': {'lat': 29.9044, 'lon': 35.0669, 'radius': 2000},

    # ============================================================================
    # MAJOR MOSHAVIM
    # ============================================================================
    'kfar_yehoshua': {'lat': 32.6831, 'lon': 35.1589, 'radius': 2000},
    'nahalal': {'lat': 32.6817, 'lon': 35.1900, 'radius': 2000},
    'kfar_yedidia': {'lat': 32.4139, 'lon': 34.9217, 'radius': 2000},
    'einat': {'lat': 32.1931, 'lon': 34.9000, 'radius': 2000},
    'beer_yaakov': {'lat': 31.9436, 'lon': 34.8364, 'radius': 2000},
    'rinnatya': {'lat': 32.0069, 'lon': 34.8189, 'radius': 2000},
    'bnei_atarot': {'lat': 32.0931, 'lon': 34.8339, 'radius': 2000},
    'kfar_netter': {'lat': 32.2672, 'lon': 34.8656, 'radius': 2000},
    'avihayil': {'lat': 32.3875, 'lon': 34.8844, 'radius': 2000},
    'bat_hadar': {'lat': 32.2500, 'lon': 34.8833, 'radius': 2000},
    'beit_herut': {'lat': 32.2500, 'lon': 34.8667, 'radius': 2000},
    'beit_halevy': {'lat': 32.3667, 'lon': 34.9000, 'radius': 2000},
    'beit_yitzhak': {'lat': 32.2167, 'lon': 34.8833, 'radius': 2000},
    'ben_shemen': {'lat': 31.9500, 'lon': 34.9167, 'radius': 2000},
    'bnei_tzion': {'lat': 32.1667, 'lon': 34.8500, 'radius': 2000},
    'burgata': {'lat': 31.6167, 'lon': 34.6500, 'radius': 2000},
    'ganei_tikva': {'lat': 32.0603, 'lon': 34.8739, 'radius': 2000},
    'gimzo': {'lat': 31.9333, 'lon': 34.9667, 'radius': 2000},
    'hadid': {'lat': 32.0500, 'lon': 34.9167, 'radius': 2000},
    'hamra': {'lat': 32.1833, 'lon': 35.5167, 'radius': 2000},
    'herut': {'lat': 32.1667, 'lon': 34.8500, 'radius': 2000},
    'kfar_ahim': {'lat': 31.7500, 'lon': 34.7833, 'radius': 2000},
    'kfar_azar': {'lat': 32.0500, 'lon': 34.8167, 'radius': 2000},
    'kfar_bin_nun': {'lat': 31.8333, 'lon': 34.9500, 'radius': 2000},
    'kfar_chaim': {'lat': 32.4333, 'lon': 34.9000, 'radius': 2000},
    'kfar_chabad': {'lat': 32.0167, 'lon': 34.8667, 'radius': 2000},
    'kfar_daniel': {'lat': 31.8167, 'lon': 34.9000, 'radius': 2000},
    'kfar_hess': {'lat': 32.2167, 'lon': 34.9000, 'radius': 2000},
    'kfar_malal': {'lat': 32.2333, 'lon': 34.9000, 'radius': 2000},
    'kfar_monash': {'lat': 31.9167, 'lon': 34.9000, 'radius': 2000},
    'kfar_rut': {'lat': 31.9667, 'lon': 34.8667, 'radius': 2000},
    'kfar_shmarya_hu': {'lat': 32.1833, 'lon': 34.8333, 'radius': 2000},
    'kfar_shmuel': {'lat': 31.9000, 'lon': 34.9333, 'radius': 2000},
    'kfar_sirkin': {'lat': 32.0833, 'lon': 34.9000, 'radius': 2000},
    'kfar_truman': {'lat': 31.9833, 'lon': 34.8333, 'radius': 2000},
    'kfar_vitkin': {'lat': 32.3833, 'lon': 34.8833, 'radius': 2000},
    'kfar_warburg': {'lat': 31.9667, 'lon': 34.9000, 'radius': 2000},
    'kfar_yona': {'lat': 32.3167, 'lon': 34.9333, 'radius': 2000},
    'mazor': {'lat': 32.0000, 'lon': 34.9167, 'radius': 2000},
    'messilat_tzion': {'lat': 32.0167, 'lon': 34.9333, 'radius': 2000},
    'mikhmoret': {'lat': 32.4167, 'lon': 34.8667, 'radius': 2000},
    'mishmeret': {'lat': 32.3500, 'lon': 34.8833, 'radius': 2000},
    'nir_zvi': {'lat': 31.9500, 'lon': 34.7833, 'radius': 2000},
    'nordiya': {'lat': 32.2833, 'lon': 34.8667, 'radius': 2000},
    'odonim': {'lat': 32.0333, 'lon': 34.9500, 'radius': 2000},
    'ofer': {'lat': 32.0667, 'lon': 34.9333, 'radius': 2000},
    'olesh': {'lat': 32.1000, 'lon': 34.9167, 'radius': 2000},
    'peta_h_tikva': {'lat': 32.0878, 'lon': 34.8878, 'radius': 2000},
    'revaha': {'lat': 31.7833, 'lon': 34.9500, 'radius': 2000},
    'rinatya': {'lat': 32.0000, 'lon': 34.8167, 'radius': 2000},
    'sdeh_warburg': {'lat': 31.9500, 'lon': 34.8833, 'radius': 2000},
    'sha_ar_efraim': {'lat': 32.2000, 'lon': 35.0333, 'radius': 2000},
    'shave_tzion': {'lat': 33.0333, 'lon': 35.1000, 'radius': 2000},
    'tzafria': {'lat': 31.8167, 'lon': 34.9333, 'radius': 2000},
    'tzur_moshe': {'lat': 32.2500, 'lon': 34.9333, 'radius': 2000},
    'udim': {'lat': 32.3167, 'lon': 35.0000, 'radius': 2000},
    'yakum': {'lat': 32.2500, 'lon': 34.8500, 'radius': 2000},
    'yanuv': {'lat': 32.0833, 'lon': 34.9333, 'radius': 2000},
    'yaakov': {'lat': 32.7667, 'lon': 35.3833, 'radius': 2000},
    'yarkona': {'lat': 32.2667, 'lon': 34.9167, 'radius': 2000},
    'zetan': {'lat': 31.8500, 'lon': 34.8833, 'radius': 2000},

    # ============================================================================
    # DEVELOPMENT TOWNS & REGIONAL CENTERS
    # ============================================================================
    'metula': {'lat': 33.2797, 'lon': 35.5786, 'radius': 2000},
    'kiryat_anavim': {'lat': 31.8106, 'lon': 35.1269, 'radius': 2000},
    'binyamina': {'lat': 32.5217, 'lon': 34.9528, 'radius': 2500},
    'caesarea': {'lat': 32.5042, 'lon': 34.8950, 'radius': 2000},
    'daliyat_al_karmel': {'lat': 32.6931, 'lon': 35.0550, 'radius': 2000},
    'isfiya': {'lat': 32.7233, 'lon': 35.0647, 'radius': 2000},
    'jish': {'lat': 33.0169, 'lon': 35.4508, 'radius': 2000},
    'ma_aleh_adumim': {'lat': 31.7722, 'lon': 35.2981, 'radius': 3000},
    'ma_ale_iron': {'lat': 32.9856, 'lon': 35.3900, 'radius': 2000},
    'mevasseret_tzion': {'lat': 31.8000, 'lon': 35.1428, 'radius': 2500},
    'metula': {'lat': 33.2797, 'lon': 35.5786, 'radius': 2000},
    'mitzpe_ramon': {'lat': 30.6097, 'lon': 34.8019, 'radius': 2500},
    'neve_ativ': {'lat': 33.2964, 'lon': 35.7508, 'radius': 2000},
    'pardesiya': {'lat': 32.2958, 'lon': 34.8561, 'radius': 2000},
    'ramot_naftali': {'lat': 33.1461, 'lon': 35.4922, 'radius': 2000},
    'rosh_pinna': {'lat': 32.9717, 'lon': 35.5450, 'radius': 2000},
    'safed': {'lat': 32.9653, 'lon': 35.4958, 'radius': 3000},
    'savyon': {'lat': 32.0378, 'lon': 34.8692, 'radius': 2000},
    'tel_sheva': {'lat': 31.2506, 'lon': 34.8419, 'radius': 2000},
    'yeruham': {'lat': 30.9886, 'lon': 34.9314, 'radius': 2500},
    'zoran': {'lat': 32.2881, 'lon': 34.9142, 'radius': 2000},
}


def setup_logging():
    """Configure logging."""
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / 'cities_landuse_download.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='a'),
            logging.StreamHandler()
        ]
    )
    logging.getLogger('osmnx').setLevel(logging.WARNING)
    logging.info(f"Logging to: {log_file}")


def download_city_landuse(city_name: str, lat: float, lon: float, radius: int):
    """
    Download landuse data for a city.

    Parameters
    ----------
    city_name : str
        City name
    lat : float
        City center latitude
    lon : float
        City center longitude
    radius : int
        Radius in meters around city center

    Returns
    -------
    GeoDataFrame or None
        Landuse features
    """
    try:
        logging.info(f"  Downloading landuse for {city_name} (r={radius}m)...")

        # Download from circular area around city center
        gdf = ox.features_from_point(
            center_point=(lat, lon),
            dist=radius,
            tags={'landuse': True}
        )

        if gdf is not None and len(gdf) > 0:
            # Keep only polygon geometries
            gdf = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]

            if len(gdf) > 0:
                logging.info(f"    [OK] Downloaded {len(gdf)} landuse features")
                return gdf

        logging.info(f"    [SKIP] No landuse features found")
        return None

    except Exception as e:
        logging.error(f"    [FAIL] Failed: {e}")
        return None


def save_city_landuse(gdf: gpd.GeoDataFrame, output_path: Path, city_name: str):
    """Save city landuse data to GPKG."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Select essential columns
        essential_cols = ['geometry', 'landuse']
        for col in ['name', 'amenity', 'natural', 'leisure']:
            if col in gdf.columns:
                essential_cols.append(col)

        available_cols = [col for col in essential_cols if col in gdf.columns]
        save_gdf = gdf[available_cols].copy()

        # Save to GPKG
        save_gdf.to_file(output_path, driver="GPKG", layer="landuse", engine="pyogrio")

        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        logging.info(f"    [OK] Saved to {output_path.name} ({file_size_mb:.2f} MB)")

    except Exception as e:
        logging.error(f"    [FAIL] Failed to save: {e}")


def main():
    setup_logging()

    logging.info("=" * 80)
    logging.info("DOWNLOAD LANDUSE FOR ISRAELI CITIES")
    logging.info("=" * 80)
    logging.info(f"Cities: {len(ISRAELI_CITIES)}")
    logging.info("=" * 80)

    output_dir = Path("data/processed/israel/cities_landuse")
    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime.now()
    success_count = 0

    for i, (city_name, info) in enumerate(ISRAELI_CITIES.items(), 1):
        logging.info(f"\n[{i}/{len(ISRAELI_CITIES)}] Processing {city_name}...")

        output_file = output_dir / f"{city_name}_landuse.gpkg"

        # Skip if exists
        if output_file.exists():
            logging.info(f"  [SKIP] Already exists")
            success_count += 1
            continue

        # Download
        gdf = download_city_landuse(
            city_name,
            info['lat'],
            info['lon'],
            info['radius']
        )

        if gdf is not None and len(gdf) > 0:
            save_city_landuse(gdf, output_file, city_name)
            success_count += 1

        # Brief pause
        time.sleep(1)

    # Summary
    elapsed = (datetime.now() - start_time).total_seconds() / 60

    logging.info("\n" + "=" * 80)
    logging.info("SUMMARY")
    logging.info("=" * 80)
    logging.info(f"Total cities: {len(ISRAELI_CITIES)}")
    logging.info(f"Successfully processed: {success_count}")
    logging.info(f"Total time: {elapsed:.1f} minutes")

    # Calculate total storage
    total_size_mb = sum(
        f.stat().st_size for f in output_dir.glob("*.gpkg")
    ) / (1024 * 1024)
    logging.info(f"Total storage: {total_size_mb:.1f} MB")

    return 0


if __name__ == '__main__':
    sys.exit(main())
