import pandas as pd
import numpy as np
import os
from dateutil import tz
from datetime import datetime, timedelta
import seaborn

###############################################
# Place DriveNow data in the path given below #
###############################################

df = pd.read_csv("Data/DTU-data-til-case_LTMZones1.csv", sep=";")
removeList = [[" ", "_"], ["(", ""], [")", ""]]
for remove, replaceWith in removeList:
    df.columns = [c.replace(remove, replaceWith) for c in df.columns]
# 'coerce' results in NaN for entries that can't be converted
df.Batteristatus_start = pd.to_numeric(df.Batteristatus_start, errors='coerce')
df.Batteristatus_slut = pd.to_numeric(df.Batteristatus_slut, errors='coerce')


# stringToDatetime
# converts dataframe colums eg. from list to type datetime with formating "%d/%m/%Y %H:%M"
def stringToDatetime(columns):
    for column in columns:
        df[column] = pd.to_datetime(df[column], dayfirst=True, format="%d/%m/%Y %H:%M")
        if column == "Reservationstidspunkt":
            breakpoint = datetime(2017,10,29,2,51)
            df.loc[((df.Reservationstidspunkt - breakpoint).astype("timedelta64[m]") > 0) & (df.TurID != 106025), column] = \
                df.loc[((df.Reservationstidspunkt - breakpoint).astype("timedelta64[m]") > 0) & (df.TurID != 106025), column] + pd.Timedelta(hours=1)
        elif column == "Start_tidspunkt":
            breakpoint = datetime(2017, 10, 29, 2, 49)
            df.loc[
                ((df.Start_tidspunkt - breakpoint).astype("timedelta64[m]") > 0) & (df.TurID != 106025), column] = \
                df.loc[((df.Start_tidspunkt - breakpoint).astype("timedelta64[m]") > 0) & (
                            df.TurID != 106025), column] + pd.Timedelta(hours=1)
        elif column == "Slut_tidspunkt":
            breakpoint = datetime(2017, 10, 29, 2, 54)
            df.loc[
                (((df.Slut_tidspunkt - breakpoint).astype("timedelta64[m]") > 0) & (df.TurID != 106024)) | (df.TurID == 106025), column] = \
                df.loc[(((df.Slut_tidspunkt - breakpoint).astype("timedelta64[m]") > 0) & (
                        df.TurID != 106024)) | (df.TurID == 106025), column] + pd.Timedelta(hours=1)
    return


stringToDatetime(["Reservationstidspunkt", "Start_tidspunkt", "Slut_tidspunkt"])
# Sorts df by BilID then Start_tidspunkt, this ensures all rides are in order and we can reference rows above as last trip
df.sort_values(by=["BilID", "Start_tidspunkt"], inplace=True)
# Dropping last 6 rows as the date for these rides are 2 months later than the last datapoint in the rest of the data
# We sort only by Start_tidspunkt, not inplace, to get the true 6 last rides regardless of BilID
df.drop(df.sort_values(by=["Start_tidspunkt"]).tail(6).index, inplace=True)
# Dropping data lines with "-" as BilID
df.drop(df[df.BilID == "-"].index, inplace=True)
# replace "," with "." in strings
for column in ["Latitude_Start", "Latitude_Slut", "Longitude_Start", "Longitude_Slut"]:
    df[column] = df[column].str.replace(",", ".").astype(float)


# function should only be used on df's filtered to only ONE BilID
def fixDataMissing(df):
    if len(df.BilID.unique()) == 1:
        print("Please provide full df and BilID as second variable!")
    else:
        # Drop all rows that start and stop in same exact X-coordinate
        df.drop(df[(df.Latitude_Start == df.shift(periods=-1).Latitude_Start) & (
                df.Latitude_Start == df.Latitude_Slut)].index, inplace=True)

        # Drop all rows that have the same start/stop coord pair and 0 Km_kørt
        df.drop(df[(df.Latitude_Start == df.Latitude_Slut) & (
                df.Longitude_Start == df.Longitude_Slut) & (df.Km_kørt <= 0)].index, inplace=True)

        # If end point data is missing, fill in start data from next trip.
        dfshift = df.shift(periods=-1)[
            (df.ToZoneID == 0) & (df.Latitude_Slut == 0) & (df.Latitude_Start != df.Latitude_Start.shift(periods=-1))]
        newValues = pd.DataFrame(data={
            "Latitude_Slut": dfshift.Latitude_Start,
            "Longitude_Slut": dfshift.Longitude_Start,
            "ToZoneID": dfshift.FromZoneID
        })
        df.loc[(df.ToZoneID == 0) & (df.Latitude_Slut == 0) & (df.Latitude_Start != df.Latitude_Start.shift(periods=-1)),
               ["Latitude_Slut", "Longitude_Slut", "ToZoneID"]] = newValues

        # If FromZoneID or ToZoneID is empty, but coords are populated, set *ZoneID=999999
        # This is a bug caused by cars parked on bridges or near water.
        df.loc[(df.ToZoneID == 0) & (df.Latitude_Slut != 0), ["ToZoneID"]] = 999999
        df.loc[(df.FromZoneID == 0) & (df.Latitude_Start != 0), ["FromZoneID"]] = 999999
    return df


def fixMultiTravel(df):
    # Column tables for fixing multi travel by same PersonID with no delay between
    mergeColumns = ["Latitude_Start", "Longitude_Start", "Reservationstidspunkt", "Start_tidspunkt",
                    "Batteristatus_start",
                    "Km_kørt", "FromZoneID", "tripDuration", "idleTime"]
    # Threshold deciding cutoff for merging trips into one
    threshold = 6

    if len(df.BilID.unique()) == 1:
        print("Please provide full df and BilID as second variable!")
    else:
        while len(df.loc[(df.PersonID == df.PersonID.shift(periods=1)) & (df.PersonID != df.PersonID.shift(periods=2))
                         & (df.idleTime <= threshold)]) != 0:
            dfshift = df.shift(periods=1)[(df.PersonID == df.PersonID.shift(periods=1)) & (
                    df.PersonID != df.PersonID.shift(periods=2)) & (df.idleTime <= threshold)]
            dfnoshift = df[(df.PersonID == df.PersonID.shift(periods=1)) & (df.PersonID != df.PersonID.shift(periods=2))
                           & (df.idleTime <= threshold)]
            mergeddf = pd.DataFrame(data={
                "Latitude_Start": dfshift.Latitude_Start,
                "Longitude_Start": dfshift.Longitude_Start,
                "Reservationstidspunkt": dfshift.Reservationstidspunkt,
                "Start_tidspunkt": dfshift.Start_tidspunkt,
                "Batteristatus_start": dfshift.Batteristatus_start,
                "Km_kørt": dfnoshift.Km_kørt + dfshift.Km_kørt,
                "FromZoneID": dfshift.FromZoneID,
                "tripDuration": dfnoshift.tripDuration + dfshift.tripDuration - dfnoshift.idleTime.astype(float),
                "idleTime": dfshift.idleTime
            })
            shiftIndex = df.shift(periods=-1)
            removeIndex = shiftIndex.loc[(shiftIndex.PersonID == shiftIndex.PersonID.shift(periods=1)) & (
                    shiftIndex.PersonID != shiftIndex.PersonID.shift(periods=2)) & (
                                                 shiftIndex.idleTime <= threshold)].index
            # Checks if trip above is driven by same PersonID and with idleTime <= 6 minutes
            # If true merge rows and delete above row
            df.loc[(df.PersonID == df.PersonID.shift(periods=1)) & (df.PersonID != df.PersonID.shift(periods=2)) & (
                    df.idleTime <= threshold), mergeColumns] = mergeddf
            df.drop(removeIndex, inplace=True)


# Adds column tripDuration in minutes to the dataframe
df["tripDuration"] = (df.Slut_tidspunkt - df.Start_tidspunkt).astype("timedelta64[m]")
# Adds column idleTime in minutes to the dataframe
df["idleTime"] = "default"
# fixing various data problems
df = fixDataMissing(df)

for BilID in df.BilID.unique():
    # df[df.BilID == BilID] = fixDataMissing(df, BilID)

    #

    # Populates column idleTime by difference in last use end minus this use start time
    df.loc[df["BilID"] == BilID, ["idleTime"]] = (df[df["BilID"] == BilID]["Start_tidspunkt"] - df[df["BilID"] == BilID]
    ["Slut_tidspunkt"].shift(periods=1)).astype("timedelta64[m]")

# merging trips within a short timespan by the same PersonID
fixMultiTravel(df)
for BilID in df.BilID.unique():
    # df[df.BilID == BilID] = fixDataMissing(df, BilID)

    #

    # Populates column idleTime by difference in last use end minus this use start time
    df.loc[df["BilID"] == BilID, ["idleTime"]] = (df[df["BilID"] == BilID]["Start_tidspunkt"] - df[df["BilID"] == BilID]
    ["Slut_tidspunkt"].shift(periods=1)).astype("timedelta64[m]")

# drops any rows with a tripDuration larger than 3 times interquantile range
def OutlierHandling(df):
    # IQRtrimming tripDuration
    K_value = 3
    q25, q75 = df.tripDuration.quantile(0.25), df.tripDuration.quantile(0.75)
    IQR = q75-q25
    cutoff = K_value*IQR
    df.drop(df[(df.tripDuration < q25-cutoff) | (df.tripDuration > q75+cutoff)].index, inplace=True)

    # Handling negative idleTime
    removeIndex = df.shift(periods=-1)[df.shift(periods=-1).idleTime < 0].index
    for index in df[df.idleTime < 0].index:
        df.loc[df.index == index, "idleTime"] = (df.Start_tidspunkt - df.Slut_tidspunkt.shift(periods=1)).astype("timedelta64[m]")
    df.drop(removeIndex, inplace=True)

    #IQRtimming idleTime
    K_value = 1.5
    q25, q75 = df.idleTime.quantile(0.25), df.idleTime.quantile(0.75)
    IQR = q75 - q25
    cutoff = K_value * IQR
    df.drop(df[(df.idleTime < q25 - cutoff) | (df.idleTime > q75 + cutoff)].index, inplace=True)

OutlierHandling(df)

df["idleTime"] = df.idleTime.astype("float64")

import plotly.express as px

fig = px.scatter_mapbox(df, lat="Latitude_Start", lon="Longitude_Start", hover_name="TurID", hover_data=["BilID","tripDuration"],
                        zoom=10, height=900, color="idleTime") # color_continuous_scale=px.colors.cyclical.IceFire
fig.update_layout(mapbox_style="open-street-map")
fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
fig.show()

# color_discrete_sequence=["fuchsia"]