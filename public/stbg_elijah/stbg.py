# -*- coding: utf-8 -*-
"""
Highway Projects Analysis Script

This script analyzes highway projects based on various criteria including:
- Safety metrics (crash frequency and rate)
- Congestion metrics (demand and level of service)
- Equity and access metrics (jobs, non-work destinations)
- Environmental sensitivity
- Economic development indicators
"""

import geopandas as gpd
import pandas as pd
import folium
import json
from shapely.geometry import Point
from functools import reduce
from pyproj import CRS
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# 1. SAFETY - CRASH FREQUENCY
# =============================================================================

def analyze_safety_frequency():
    """Analyze safety based on crash frequency within project buffers"""
    
    # Load data
    gdf = gpd.read_file(r'projects.geojson')
    crashes = gpd.read_file(r'crashes.geojson')
    
    # Ensure projected CRS for buffer
    gdf = gdf.to_crs(epsg=2263)  # feet
    crashes = crashes.to_crs(gdf.crs)
    
    # Add project_id if not present
    if "project_id" not in gdf.columns:
        gdf["project_id"] = range(1, len(gdf) + 1)
    
    # Create 250 ft buffer
    gdf_buffered = gdf.copy()
    gdf_buffered["geometry"] = gdf_buffered.geometry.buffer(250)
    
    # Select crashes that intersect buffer
    crashes_in_buffer = gpd.sjoin(
        crashes,
        gdf_buffered[["project_id", "geometry"]],
        how="inner",
        predicate="intersects"
    )
    
    # Summarize crash people counts per buffer
    crash_sums = crashes_in_buffer.groupby("project_id").agg({
        "K_PEOPLE": "sum",
        "A_PEOPLE": "sum",
        "B_PEOPLE": "sum",
        "C_PEOPLE": "sum"
    }).reset_index()
    
    # Merge summary back to buffers
    gdf_buffered = gdf_buffered.merge(crash_sums, on="project_id", how="left")
    gdf_buffered.fillna(0, inplace=True)
    
    # Reproject back to WGS84 for saving/visualization
    gdf_buffered = gdf_buffered.to_crs(epsg=4326)
    
    # Calculate EPDO
    gdf_buffered["EPDO"] = (
        gdf_buffered["K_PEOPLE"] * 2715000 +
        gdf_buffered["A_PEOPLE"] * 2715000 +
        gdf_buffered["B_PEOPLE"] * 300000 +
        gdf_buffered["C_PEOPLE"] * 170000
    )
    
    # Calculate benefit = EPDO * (1 - cmf)
    gdf_buffered["benefit"] = gdf_buffered["EPDO"] * (1 - gdf_buffered["cmf"])
    
    # Calculate safety score
    max_benefit = gdf_buffered["benefit"].max()
    
    # Avoid divide by zero
    if max_benefit > 0:
        gdf_buffered["safety_freq"] = (gdf_buffered["benefit"] / max_benefit) * 50
    else:
        gdf_buffered["safety_freq"] = 0
    
    safety_freq = gdf_buffered[['project_id', 'safety_freq']]
    return safety_freq

# =============================================================================
# 2. SAFETY - CRASH RATE
# =============================================================================

def analyze_safety_rate():
    """Analyze safety based on crash rate (normalized by traffic volume)"""
    
    # Load and process data
    gdf = gpd.read_file(r'projects.geojson')
    crashes = gpd.read_file(r'crashes.geojson')
    
    # Process data similar to safety frequency analysis
    gdf_buffered = gdf.to_crs(epsg=2263)
    crashes = crashes.to_crs(gdf.crs)
    
    if "project_id" not in gdf.columns:
        gdf["project_id"] = range(1, len(gdf) + 1)
    
    gdf_buffered = gdf.copy()
    gdf_buffered["geometry"] = gdf_buffered.geometry.buffer(250)
    
    crashes_in_buffer = gpd.sjoin(
        crashes,
        gdf_buffered[["project_id", "geometry"]],
        how="inner",
        predicate="intersects"
    )
    
    crash_sums = crashes_in_buffer.groupby("project_id").agg({
        "K_PEOPLE": "sum",
        "A_PEOPLE": "sum",
        "B_PEOPLE": "sum",
        "C_PEOPLE": "sum"
    }).reset_index()
    
    gdf_buffered = gdf_buffered.merge(crash_sums, on="project_id", how="left")
    gdf_buffered.fillna(0, inplace=True)
    gdf_buffered = gdf_buffered.to_crs(epsg=4326)
    
    gdf_buffered["EPDO"] = (
        gdf_buffered["K_PEOPLE"] * 2715000 +
        gdf_buffered["A_PEOPLE"] * 2715000 +
        gdf_buffered["B_PEOPLE"] * 300000 +
        gdf_buffered["C_PEOPLE"] * 170000
    )
    
    gdf_buffered["benefit"] = gdf_buffered["EPDO"] * (1 - gdf_buffered["cmf"])
    
    # Define epdo_rate based on project type
    def calculate_epdo_rate_and_vmt(row):
        if row["type"].lower() == "highway":
            vmt = row["AADT"] * row["length"] * 365 / 100_000_000
        elif row["type"].lower() == "intersection":
            vmt = row["AADT"] * 365 / 1_000_000
        else:
            vmt = 1  # avoid division by zero
        epdo_rate = row["benefit"] / vmt if vmt != 0 else 0
        return pd.Series({"VMT": vmt, "epdo_rate": epdo_rate})
    
    # Apply function
    gdf_buffered[["VMT", "epdo_rate"]] = gdf_buffered.apply(calculate_epdo_rate_and_vmt, axis=1)
    
    # Calculate safety_rate
    max_rate = gdf_buffered["epdo_rate"].max()
    
    # Avoid division by zero
    if max_rate > 0:
        gdf_buffered["safety_rate"] = (gdf_buffered["epdo_rate"] / max_rate) * 50
    else:
        gdf_buffered["safety_rate"] = 0
    
    safety_rate = gdf_buffered[['project_id', 'safety_rate']]
    return safety_rate

# =============================================================================
# 3. CONGESTION - DEMAND
# =============================================================================

def analyze_congestion_demand():
    """Analyze congestion based on traffic demand"""
    
    # Load projects
    projects = gpd.read_file(r'projects.geojson')
    
    # Load AADT segments
    aadt = gpd.read_file(r'stbg_aadt.geojson')
    
    # Ensure both are in the same CRS
    projects = projects.to_crs(epsg=2283)  # Virginia State Plane
    aadt = aadt.to_crs(projects.crs)
    
    buffer_distance = 0.25 * 1609.34  # meters
    projects["buffer"] = projects.geometry.buffer(buffer_distance)
    
    # Convert project buffers to GeoDataFrame
    project_buffers = projects.set_geometry("buffer")
    
    # Perform spatial join
    intersected = gpd.sjoin(aadt, project_buffers, how="inner", predicate="intersects")
    
    intersected["segment_mileage"] = intersected.geometry.length / 1609.34  # meters → miles
    intersected["vmt"] = intersected["aadt_0"] * intersected["segment_mileage"]
    
    wa_aadt = (
        intersected.groupby("project_id")
        .apply(lambda x: x["vmt"].sum() / x["segment_mileage"].sum())
        .reset_index(name="wa_aadt")
    )
    
    # Drop any existing wa_aadt columns to avoid _x/_y
    projects = projects.drop(columns=[col for col in projects.columns if "wa_aadt" in col], errors="ignore")
    
    # Merge the computed wa_aadt
    projects = projects.merge(wa_aadt, on="project_id", how="left")
    
    # Replace NaN with 0
    projects["wa_aadt"] = projects["wa_aadt"].fillna(0)
    
    # Normalize
    projects["cong_demand"] = (projects["wa_aadt"] / projects["wa_aadt"].max()) * 10
    projects = projects[['project_id', 'cong_demand']]
    
    return projects

# =============================================================================
# 4. CONGESTION - LEVEL OF SERVICE
# =============================================================================

def analyze_congestion_los():
    """Analyze congestion based on Level of Service"""
    
    # Load project and AADT layers
    projects = gpd.read_file(r'projects.geojson')
    aadt = gpd.read_file(r'stbg_aadt.geojson')
    
    # Create cong_value column based on los_0
    los_mapping = {
        "A": 0,
        "B": 1,
        "C": 2,
        "D": 3,
        "E": 3,
        "F": 3
    }
    
    aadt["cong_value"] = aadt["los_0"].map(los_mapping)
    
    # Create 0.25 mile buffer around project locations
    projects = projects.to_crs(epsg=3857)  # project to metric CRS
    aadt = aadt.to_crs(epsg=3857)
    
    projects["buffer"] = projects.geometry.buffer(402.336)
    
    # Intersect buffer and AADT segments
    projects_exploded = projects.explode(index_parts=False)
    intersected = gpd.overlay(aadt, gpd.GeoDataFrame(geometry=projects_exploded["buffer"]), how="intersection")
    
    # Sum cong_value for all segments in each project buffer
    intersected = intersected.merge(projects[["project_id", "buffer"]], left_on='geometry', right_on='buffer', how='left')
    
    project_cong = (
        intersected.groupby("project_id")["cong_value"]
        .sum()
        .reset_index(name="sum_cong_value")
    )
    
    # Merge back to projects
    projects = projects.merge(project_cong, on="project_id", how="left")
    projects["sum_cong_value"] = projects["sum_cong_value"].fillna(0)
    
    # Normalize
    normalized = (projects["sum_cong_value"] / projects["sum_cong_value"].max()) * 5
    # If indivisible (not integer), return 0
    projects["cong_los"] = normalized.where(normalized % 1 == 0, 0)
    
    projects = projects[['project_id', 'cong_los']]
    
    return projects

# =============================================================================
# 5. EQUITY/ACCESS - ACCESS TO JOBS
# =============================================================================

def analyze_equity_access_jobs():
    """Analyze equity and access to jobs"""
    
    # Load datasets
    pop_emp_df = gpd.read_file(r"pop_emp_df.geojson")
    projects = gpd.read_file(r'projects.geojson')
    
    # Define buffer distances in meters
    fc_distances_miles = {"PA": 10, "MA": 7.5, "MC": 5}
    mile_to_meter = 1609.34
    fc_distances_m = {k: v * mile_to_meter for k, v in fc_distances_miles.items()}
    
    # Project both datasets to a projected CRS
    projects = projects.to_crs(epsg=2283)
    pop_emp_df = pop_emp_df.to_crs(epsg=2283)
    
    # Calculate TAZ centroids
    pop_emp_df["centroid"] = pop_emp_df.geometry.centroid
    
    results = []
    
    # For each project
    for _, proj in projects.iterrows():
        fc = proj["fc"]
        buffer_dist = fc_distances_m[fc]
        
        # Create buffer
        proj_buffer = proj.geometry.buffer(buffer_dist)
        
        # Select TAZs with centroid inside buffer
        selected = pop_emp_df[pop_emp_df["centroid"].within(proj_buffer)]
        
        # Aggregate employment
        sum_emp17 = selected["emp17"].sum()
        sum_emp50 = selected["emp50"].sum()
        
        # % change
        pct_change = ((sum_emp50 - sum_emp17) / sum_emp17 * 100) if sum_emp17 != 0 else 0
        
        results.append({
            "project_id": proj["project_id"],
            "sum_emp17": sum_emp17,
            "sum_emp50": sum_emp50,
            "pct_change": pct_change
        })
    
    # Convert to DataFrame
    results_df = pd.DataFrame(results)
    
    results_df["jobs_pc"] = (results_df["pct_change"] / results_df["pct_change"].max()) * 5 if results_df["pct_change"].max() != 0 else 0
    
    results_df = results_df[['project_id', 'jobs_pc']]
    
    return results_df

# =============================================================================
# 6. EQUITY/ACCESS - ACCESS TO JOBS (ENVIRONMENTAL JUSTICE)
# =============================================================================

def analyze_equity_access_jobs_ej():
    """Analyze equity and access to jobs in environmental justice areas"""
    
    # Load datasets
    pop_emp_df = gpd.read_file(r"pop_emp_df.geojson")
    ej = gpd.read_file(r"t6.geojson")
    projects = gpd.read_file(r'projects.geojson')
    
    # Distances in miles → meters
    fc_distances_miles = {"PA": 10, "MA": 7.5, "MC": 5}
    mile_to_meter = 1609.34
    fc_distances_m = {k: v * mile_to_meter for k, v in fc_distances_miles.items()}
    
    # Project all layers to a projected CRS
    projects = projects.to_crs(epsg=2283)
    pop_emp_df = pop_emp_df.to_crs(epsg=2283)
    ej = ej.to_crs(epsg=2283)
    
    results = []
    
    # Loop through projects
    for _, proj in projects.iterrows():
        fc = proj["fc"]
        buffer_dist = fc_distances_m[fc]
        
        # Create buffer
        proj_buffer = proj.geometry.buffer(buffer_dist)
        
        # Clip EJ polygons within buffer
        ej_clip = ej[ej.intersects(proj_buffer)]
        
        if ej_clip.empty:
            sum_emp17 = 0
            sum_emp50 = 0
        else:
            # Clip TAZ by EJ polygons (intersection)
            taz_ej_intersect = gpd.overlay(pop_emp_df, ej_clip, how="intersection")
            
            # Aggregate employment in intersected areas
            sum_emp17 = taz_ej_intersect["emp17"].sum()
            sum_emp50 = taz_ej_intersect["emp50"].sum()
        
        # % change
        pct_change = ((sum_emp50 - sum_emp17) / sum_emp17 * 100) if sum_emp17 != 0 else 0
        
        results.append({
            "project_id": proj["project_id"],
            "sum_emp17": sum_emp17,
            "sum_emp50": sum_emp50,
            "pct_change": pct_change
        })
    
    # Results DataFrame
    results_df = pd.DataFrame(results)
    
    # Normalize percent change
    results_df["jobs_pc_ej"] = (results_df["pct_change"] / results_df["pct_change"].max()) * 5 if results_df["pct_change"].max() != 0 else 0
    results_df = results_df[['project_id', 'jobs_pc_ej']]
    
    return results_df

# =============================================================================
# 7. ACCESS TO NON-WORK DESTINATIONS
# =============================================================================

def analyze_access_non_work():
    """Analyze access to non-work destinations"""
    
    # Load datasets
    pop_emp_df = gpd.read_file(r"pop_emp_df.geojson")
    nw = gpd.read_file(r"nw.geojson")
    projects = gpd.read_file(r'projects.geojson')
    
    # Distances (miles -> meters)
    fc_distances_miles = {"PA": 10, "MA": 7.5, "MC": 5}
    mile_to_meter = 1609.34
    fc_distances_m = {k: v * mile_to_meter for k, v in fc_distances_miles.items()}
    
    # Project to planar CRS
    projects = projects.to_crs(epsg=2283)
    nw = nw.to_crs(epsg=2283)
    pop_emp_df = pop_emp_df.to_crs(epsg=2283)
    
    results = []
    
    for _, proj in projects.iterrows():
        fc = proj["fc"]
        buffer_dist = fc_distances_m[fc]
        
        # Buffer project
        proj_buffer = proj.geometry.buffer(buffer_dist)
        
        # Count NW points inside buffer
        nw_count = nw[nw.within(proj_buffer)].shape[0]
        
        # Intersect TAZs with buffer
        taz_selected = pop_emp_df[pop_emp_df.intersects(proj_buffer)]
        
        if taz_selected.empty:
            sum_emp2017 = sum_emp2050 = sum_pop2017 = sum_pop2050 = area_sqmi = 0
        else:
            sum_emp2017 = taz_selected["emp17"].sum()
            sum_emp2050 = taz_selected["emp50"].sum()
            sum_pop2017 = taz_selected["pop17"].sum()
            sum_pop2050 = taz_selected["pop50"].sum()
            
            # area in square miles
            area_sqmi = taz_selected.to_crs(epsg=3857).geometry.area.sum() / (1609.34**2)
        
        # Calculate density metrics
        if area_sqmi > 0:
            pop_emp_den_2017 = nw_count * (sum_emp2017 + sum_pop2017) / area_sqmi
            pop_emp_den_2050 = nw_count * (sum_emp2050 + sum_pop2050) / area_sqmi
        else:
            pop_emp_den_2017 = pop_emp_den_2050 = 0
        
        results.append({
            "project_id": proj["project_id"],
            "nw_count": nw_count,
            "sum_emp2017": sum_emp2017,
            "sum_emp2050": sum_emp2050,
            "sum_pop2017": sum_pop2017,
            "sum_pop2050": sum_pop2050,
            "area_sqmi": area_sqmi,
            "pop_emp_den_2017": pop_emp_den_2017,
            "pop_emp_den_2050": pop_emp_den_2050
        })
    
    # Results dataframe
    results_df = pd.DataFrame(results)
    
    # Percent change in pop_emp_den
    results_df["access_nw_pct"] = (
        ((results_df["pop_emp_den_2050"] - results_df["pop_emp_den_2017"]) / results_df["pop_emp_den_2017"] * 100)
        .fillna(0)  # handle division by zero
    )
    
    # Normalize percent change to 0–5 scale
    results_df["access_nw_norm"] = (
        (results_df["access_nw_pct"] / results_df["access_nw_pct"].max() * 5) 
        if results_df["access_nw_pct"].max() != 0 else 0
    )
    
    results_df = results_df[['project_id', 'access_nw_norm']]
    
    return results_df

# =============================================================================
# 8. ACCESS TO NON-WORK DESTINATIONS (ENVIRONMENTAL JUSTICE)
# =============================================================================

def analyze_access_non_work_ej():
    """Analyze access to non-work destinations in environmental justice areas"""
    
    # Load datasets
    pop_emp_df = gpd.read_file(r"pop_emp_df.geojson")
    nw = gpd.read_file(r"nw.geojson")
    t6 = gpd.read_file(r"t6.geojson")
    projects = gpd.read_file(r'projects.geojson')
    
    # Distances (miles -> meters)
    fc_distances_miles = {"PA": 10, "MA": 7.5, "MC": 5}
    mile_to_meter = 1609.34
    fc_distances_m = {k: v * mile_to_meter for k, v in fc_distances_miles.items()}
    
    # Project to planar CRS
    projects = projects.to_crs(epsg=2283)
    nw = nw.to_crs(epsg=2283)
    pop_emp_df = pop_emp_df.to_crs(epsg=2283)
    t6 = t6.to_crs(epsg=2283)
    
    results = []
    
    for _, proj in projects.iterrows():
        fc = proj["fc"]
        buffer_dist = fc_distances_m[fc]
        
        # Buffer project
        proj_buffer = proj.geometry.buffer(buffer_dist)
        
        # Count NW points inside buffer AND inside T6 polygon
        nw_count = nw[nw.within(proj_buffer) & nw.within(t6.unary_union)].shape[0]
        
        # Intersect TAZs with buffer AND T6 polygon
        taz_selected = pop_emp_df[pop_emp_df.intersects(proj_buffer) & pop_emp_df.intersects(t6.unary_union)]
        
        if taz_selected.empty:
            sum_emp2017 = sum_emp2050 = sum_pop2017 = sum_pop2050 = area_sqmi = 0
        else:
            sum_emp2017 = taz_selected["emp17"].sum()
            sum_emp2050 = taz_selected["emp50"].sum()
            sum_pop2017 = taz_selected["pop17"].sum()
            sum_pop2050 = taz_selected["pop50"].sum()
            
            # area in square miles
            area_sqmi = taz_selected.to_crs(epsg=3857).geometry.area.sum() / (1609.34**2)
        
        # Calculate density metrics
        if area_sqmi > 0:
            pop_emp_den_2017 = nw_count * (sum_emp2017 + sum_pop2017) / area_sqmi
            pop_emp_den_2050 = nw_count * (sum_emp2050 + sum_pop2050) / area_sqmi
        else:
            pop_emp_den_2017 = pop_emp_den_2050 = 0
        
        results.append({
            "project_id": proj["project_id"],
            "nw_count": nw_count,
            "sum_emp2017": sum_emp2017,
            "sum_emp2050": sum_emp2050,
            "sum_pop2017": sum_pop2017,
            "sum_pop2050": sum_pop2050,
            "area_sqmi": area_sqmi,
            "pop_emp_den_2017": pop_emp_den_2017,
            "pop_emp_den_2050": pop_emp_den_2050
        })
    
    # Results dataframe
    results_df = pd.DataFrame(results)
    
    # Percent change in pop_emp_den
    results_df["access_nw_pct"] = (
        ((results_df["pop_emp_den_2050"] - results_df["pop_emp_den_2017"]) / results_df["pop_emp_den_2017"] * 100)
        .fillna(0)  # handle division by zero
    )
    
    # Normalize percent change to 0–5 scale
    max_pct = results_df["access_nw_pct"].max()
    results_df["access_nw_ej_norm"] = (results_df["access_nw_pct"] / max_pct * 5) if max_pct != 0 else 0
    
    results_df = results_df[['project_id', 'access_nw_ej_norm']]
    
    return results_df

# =============================================================================
# 9. SENSITIVE FEATURES ANALYSIS
# =============================================================================

def analyze_sensitive_features():
    """Analyze impact on sensitive environmental features"""
    
    # Load sensitive feature datasets
    hopewell_fhz = gpd.read_file(r"hopewell_fhz.geojson")
    hopewell_frsk = gpd.read_file(r"hopewell_frsk.geojson")
    hopewell_wet = gpd.read_file(r"hopewell_wet.geojson")
    hopewell_con = gpd.read_file(r"hopewell_con.geojson")
    
    # Filter AE zones
    hopewell_fhz_filtered = hopewell_fhz[hopewell_fhz['FLD_ZONE'] == 'AE']
    
    # Buffer flood risk areas
    gdf = hopewell_frsk.copy()
    if hopewell_frsk.crs is None or not hopewell_frsk.crs.is_projected:
        gdf = hopewell_frsk.to_crs('EPSG:2264')
    
    hopewell_frsk_buff = hopewell_frsk.buffer(200)
    hopewell_frsk_buff = gpd.GeoDataFrame(geometry=hopewell_frsk_buff, crs=hopewell_frsk.crs)
    
    # Combine all sensitive areas
    gdf1 = hopewell_fhz_filtered.copy()
    gdf2 = hopewell_frsk_buff.copy()
    gdf3 = hopewell_wet.copy()
    gdf4 = hopewell_con.copy()
    
    # Ensure all have the same CRS
    target_crs = gdf1.crs
    gdf2 = gdf2.to_crs(target_crs)
    gdf3 = gdf3.to_crs(target_crs)
    gdf4 = gdf4.to_crs(target_crs)
    
    # Combine all GeoDataFrames
    combined_gdf = gpd.GeoDataFrame(pd.concat([gdf1, gdf2, gdf3, gdf4], ignore_index=True))
    
    # Dissolve all geometries into one
    sen_areas = combined_gdf.dissolve()
    
    # Load projects
    gdf = gpd.read_file(r'projects.geojson')
    
    # Create ¼-mile buffer around project points
    utm_crs = gdf.estimate_utm_crs()
    gdf_utm = gdf.to_crs(utm_crs)
    
    # Create ¼-mile buffer (402.336 meters) around each project point
    buffer_distance_m = 402.336
    project_buffers = gdf_utm.buffer(buffer_distance_m)
    
    # Convert back to GeoDataFrame with original project attributes
    project_buffer_gdf = gpd.GeoDataFrame(
        gdf.drop(columns='geometry'),  # Keep all attributes except original geometry
        geometry=project_buffers,
        crs=utm_crs
    )
    project_buffer_gdf = project_buffer_gdf.to_crs(gdf.crs)
    
    # Perform intersection between project buffers and sensitive areas
    if project_buffer_gdf.crs != sen_areas.crs:
        sen_areas = sen_areas.to_crs(project_buffer_gdf.crs)
    
    sen_areas_proj_buff = gpd.overlay(project_buffer_gdf, sen_areas, how='intersection')
    
    # Compute area in square miles
    sen_areas_proj_buff["sen_area_sqmi"] = sen_areas_proj_buff.geometry.area / 2.59e6  # convert from m² to mi²
    
    cols = ["project_id", "type", "syip", "county", "cmf", "AADT", "length", "fc", "cost_mil", "tier", "sen_area_sqmi"]
    sen_areas_proj_buff = sen_areas_proj_buff[cols + ["geometry"]]
    
    # Calculate impact based on project tier
    def adjust_area(row):
        if row["tier"] == "CE":
            return row["sen_area_sqmi"] * 0.9
        elif row["tier"] == "EA":
            return row["sen_area_sqmi"] * 0.7
        elif row["tier"] == "EIS":
            return row["sen_area_sqmi"] * 0.5
        else:
            return row["sen_area_sqmi"]  # no reduction if tier not listed
    
    sen_areas_proj_buff["sen_impact"] = sen_areas_proj_buff.apply(adjust_area, axis=1)
    
    return sen_areas_proj_buff

# =============================================================================
# MAIN ANALYSIS FUNCTION
# =============================================================================

def main():
    """Main function to run all analyses and generate final ranking"""
    
    print("Starting highway projects analysis...")
    
    # Run all analyses
    print("1. Analyzing safety frequency...")
    safety_freq = analyze_safety_frequency()
    
    print("2. Analyzing safety rate...")
    safety_rate = analyze_safety_rate()
    
    print("3. Analyzing congestion demand...")
    cong_demand = analyze_congestion_demand()
    
    print("4. Analyzing congestion level of service...")
    cong_los = analyze_congestion_los()
    
    print("5. Analyzing equity and access to jobs...")
    eq_acc_jobs = analyze_equity_access_jobs()
    
    print("6. Analyzing equity and access to jobs (EJ)...")
    eq_acc_jobs_ej = analyze_equity_access_jobs_ej()
    
    print("7. Analyzing access to non-work destinations...")
    eq_acc_nw = analyze_access_non_work()
    
    print("8. Analyzing access to non-work destinations (EJ)...")
    eq_acc_nw_ej = analyze_access_non_work_ej()
    
    print("9. Analyzing sensitive features...")
    sen_features = analyze_sensitive_features()
    
    # Load original project data
    gdf = gpd.read_file(r'projects.geojson')
    
    # Combine all dataframes
    dfs = [
        safety_freq,
        safety_rate,
        cong_demand,
        cong_los,
        eq_acc_jobs,
        eq_acc_jobs_ej,
        eq_acc_nw,
        eq_acc_nw_ej
    ]
    
    # Merge all the regular dataframes on 'project_id'
    merged_data_df = reduce(lambda left, right: pd.merge(left, right, on="project_id", how="outer"), dfs)
    
    # Extract the non-geometry data from the GeoDataFrame
    gdf_data = gdf
    
    # Merge the combined data with the GeoDataFrame's attribute data
    final_attributes_df = pd.merge(merged_data_df, gdf_data, on="project_id", how="outer")
    
    # Join this final attribute table back to the original GeoDataFrame to get the geometry
    final_gdf = gdf[['project_id', 'geometry']].merge(final_attributes_df, on='project_id', how='right')
    
    # Handle multiple geometry columns - drop any extra geometry columns
    geometry_columns = [col for col in final_gdf.columns if final_gdf[col].dtype == 'geometry']
    if len(geometry_columns) > 1:
        print(f"Found multiple geometry columns: {geometry_columns}")
        # Keep only the main geometry column, drop others
        for geom_col in geometry_columns[1:]:
            final_gdf = final_gdf.drop(columns=[geom_col])
        print(f"Keeping only '{geometry_columns[0]}' geometry column")
    
    # Calculate the total benefit score
    benefit_columns = [
        'safety_freq', 
        'safety_rate', 
        'cong_demand', 
        'cong_los', 
        'jobs_pc', 
        'jobs_pc_ej', 
        'access_nw_norm', 
        'access_nw_ej_norm'
    ]
    
    # Sum the selected columns to create a new 'benefit' column
    final_gdf['benefit'] = final_gdf[benefit_columns].sum(axis=1)
    
    # Calculate the Benefit-Cost Ratio (BCR)
    final_gdf['bcr'] = final_gdf['benefit'] / final_gdf['cost_mil']
    
    # Rank the projects based on the BCR (higher BCR is better)
    final_gdf['rank'] = final_gdf['bcr'].rank(ascending=False, method='dense').astype(int)
    
    # Show the results sorted by the best BCR
    rank = final_gdf[['project_id','safety_freq','safety_rate','cong_demand','cong_los',
                     'jobs_pc','jobs_pc_ej','access_nw_norm','access_nw_ej_norm',
                     'type', 'county', 'benefit', 'cost_mil', 'bcr', 'rank']].sort_values('rank')
    
    print("\nFinal Project Rankings:")
    print(rank)
    
    # Save results - ensure only one geometry column exists
    try:
        final_gdf.to_file("final_analysis_results.geojson", driver='GeoJSON')
        print("✓ Saved final_analysis_results.geojson")
    except ValueError as e:
        print(f"Error saving GeoJSON: {e}")
        print("Saving as CSV instead...")
        # Convert geometry to WKT for CSV export
        final_gdf_copy = final_gdf.copy()
        final_gdf_copy['geometry_wkt'] = final_gdf_copy['geometry'].apply(lambda x: x.wkt)
        final_gdf_copy = final_gdf_copy.drop(columns=['geometry'])
        final_gdf_copy.to_csv("final_analysis_results.csv", index=False)
        print("✓ Saved final_analysis_results.csv")
    
    rank.to_csv("project_rankings.csv", index=False)
    print("✓ Saved project_rankings.csv")
    
    print("\nAnalysis complete!")
    
    return final_gdf, rank

# =============================================================================
# EXECUTION
# =============================================================================

if __name__ == "__main__":
    final_results, rankings = main()