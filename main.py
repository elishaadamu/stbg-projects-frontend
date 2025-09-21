import os
import tempfile
import json
from typing import List, Dict, Any
import pandas as pd
import geopandas as gpd
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncio
from functools import reduce
import numpy as np
from shapely.geometry import Point
import warnings
warnings.filterwarnings('ignore')

# Get allowed origins from environment variable
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://stbg-projects.netlify.app"
]

app = FastAPI(title="STBG Project Prioritization API", version="1.0.0")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Accept",
        "Origin",
        "X-Requested-With"
    ],
    expose_headers=["Content-Type"]
)

class AnalysisResults(BaseModel):
    projects: List[Dict[str, Any]]
    summary: Dict[str, Any]

class STBGAnalyzer:
    def __init__(self):
        self.projects_gdf = None
        self.crashes_gdf = None
        self.aadt_gdf = None
        self.pop_emp_gdf = None
        self.ej_gdf = None
        self.nw_gdf = None
        
    def load_geospatial_data(self, files_dict: Dict[str, str]):
        """Load all geospatial data files"""
        try:
            self.projects_gdf = gpd.read_file(files_dict['projects'])
            self.crashes_gdf = gpd.read_file(files_dict['crashes'])
            self.aadt_gdf = gpd.read_file(files_dict['aadt'])
            self.pop_emp_gdf = gpd.read_file(files_dict['pop_emp'])
            self.ej_gdf = gpd.read_file(files_dict['ej_areas'])
            self.nw_gdf = gpd.read_file(files_dict['non_work_dest'])
            
            # Add project_id if not present
            if "project_id" not in self.projects_gdf.columns:
                self.projects_gdf["project_id"] = range(1, len(self.projects_gdf) + 1)
                
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error loading geospatial data: {str(e)}")
    
    def calculate_safety_frequency(self) -> pd.DataFrame:
        """Calculate safety frequency score based on crash data"""
        try:
            # Ensure projected CRS for buffer
            gdf = self.projects_gdf.to_crs(epsg=2263)  # feet
            crashes = self.crashes_gdf.to_crs(gdf.crs)
            
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
            crash_cols = []
            for col in ["K_PEOPLE", "A_PEOPLE", "B_PEOPLE", "C_PEOPLE"]:
                if col in crashes_in_buffer.columns:
                    crash_cols.append(col)
            
            if crash_cols:
                crash_sums = crashes_in_buffer.groupby("project_id")[crash_cols].sum().reset_index()
                # Merge summary back to buffers
                gdf_buffered = gdf_buffered.merge(crash_sums, on="project_id", how="left")
                gdf_buffered[crash_cols] = gdf_buffered[crash_cols].fillna(0)
                
                # Calculate EPDO
                epdo_weights = {"K_PEOPLE": 2715000, "A_PEOPLE": 2715000, "B_PEOPLE": 300000, "C_PEOPLE": 170000}
                gdf_buffered["EPDO"] = sum(gdf_buffered[col] * epdo_weights.get(col, 0) for col in crash_cols)
                
                # Calculate benefit = EPDO * (1 - cmf)
                if "cmf" in gdf_buffered.columns:
                    gdf_buffered["benefit"] = gdf_buffered["EPDO"] * (1 - gdf_buffered["cmf"])
                else:
                    gdf_buffered["benefit"] = gdf_buffered["EPDO"]
            else:
                gdf_buffered["benefit"] = 0
            
            # Calculate safety score
            max_benefit = gdf_buffered["benefit"].max() if gdf_buffered["benefit"].max() > 0 else 1
            gdf_buffered["safety_freq"] = (gdf_buffered["benefit"] / max_benefit) * 50
            
            return gdf_buffered[['project_id', 'safety_freq']]
            
        except Exception as e:
            print(f"Error in safety frequency calculation: {e}")
            # Return default values
            return pd.DataFrame({
                'project_id': self.projects_gdf['project_id'],
                'safety_freq': [0] * len(self.projects_gdf)
            })
    
    def calculate_safety_rate(self, safety_freq_df: pd.DataFrame) -> pd.DataFrame:
        """Calculate safety rate score"""
        try:
            gdf_buffered = self.projects_gdf.merge(safety_freq_df, on="project_id", how="left")
            
            # Function to calculate epdo_rate and VMT
            def calculate_epdo_rate_and_vmt(row):
                if "benefit" not in row or pd.isna(row.get("benefit", 0)):
                    benefit = row.get("safety_freq", 0) * 100  # Estimate benefit from frequency
                else:
                    benefit = row["benefit"]
                    
                if row.get("type", "").lower() == "highway":
                    vmt = row.get("AADT", 10000) * row.get("length", 1) * 365 / 100_000_000
                elif row.get("type", "").lower() == "intersection":
                    vmt = row.get("AADT", 10000) * 365 / 1_000_000
                else:
                    vmt = 1
                
                epdo_rate = benefit / vmt if vmt != 0 else 0
                return pd.Series({"VMT": vmt, "epdo_rate": epdo_rate})
            
            gdf_buffered[["VMT", "epdo_rate"]] = gdf_buffered.apply(calculate_epdo_rate_and_vmt, axis=1)
            
            # Calculate safety_rate
            max_rate = gdf_buffered["epdo_rate"].max() if gdf_buffered["epdo_rate"].max() > 0 else 1
            gdf_buffered["safety_rate"] = (gdf_buffered["epdo_rate"] / max_rate) * 50
            
            return gdf_buffered[['project_id', 'safety_rate']]
            
        except Exception as e:
            print(f"Error in safety rate calculation: {e}")
            return pd.DataFrame({
                'project_id': self.projects_gdf['project_id'],
                'safety_rate': [0] * len(self.projects_gdf)
            })
    
    def calculate_congestion_demand(self) -> pd.DataFrame:
        """Calculate congestion demand score"""
        try:
            projects = self.projects_gdf.to_crs(epsg=2283)
            aadt = self.aadt_gdf.to_crs(projects.crs)
            
            buffer_distance = 0.25 * 1609.34  # meters
            projects["buffer"] = projects.geometry.buffer(buffer_distance)
            project_buffers = projects.set_geometry("buffer")
            
            # Perform spatial join
            intersected = gpd.sjoin(aadt, project_buffers, how="inner", predicate="intersects")
            
            # Calculate weighted average AADT
            intersected["segment_mileage"] = intersected.geometry.length / 1609.34
            
            # Handle different AADT column names
            aadt_col = None
            for col in ["aadt_0", "aadt", "AADT", "volume"]:
                if col in intersected.columns:
                    aadt_col = col
                    break
            
            if aadt_col:
                intersected["vmt"] = intersected[aadt_col] * intersected["segment_mileage"]
                wa_aadt = (
                    intersected.groupby("project_id")
                    .apply(lambda x: x["vmt"].sum() / x["segment_mileage"].sum() if x["segment_mileage"].sum() > 0 else 0, include_groups=False)
                    .reset_index(name="wa_aadt")
                )
            else:
                # Use default values if no AADT column found
                wa_aadt = pd.DataFrame({
                    'project_id': projects['project_id'],
                    'wa_aadt': [10000] * len(projects)
                })
            
            projects = projects.merge(wa_aadt, on="project_id", how="left")
            projects["wa_aadt"] = projects["wa_aadt"].fillna(0)
            
            # Normalize
            max_aadt = projects["wa_aadt"].max() if projects["wa_aadt"].max() > 0 else 1
            projects["cong_demand"] = (projects["wa_aadt"] / max_aadt) * 10
            
            return projects[['project_id', 'cong_demand']]
            
        except Exception as e:
            print(f"Error in congestion demand calculation: {e}")
            return pd.DataFrame({
                'project_id': self.projects_gdf['project_id'],
                'cong_demand': [0] * len(self.projects_gdf)
            })
    
    def calculate_congestion_los(self) -> pd.DataFrame:
        """Calculate congestion level of service score"""
        try:
            projects = self.projects_gdf.to_crs(epsg=3857)
            aadt = self.aadt_gdf.to_crs(epsg=3857)
            
            # LOS mapping
            los_mapping = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 3, "F": 3}
            
            # Handle different LOS column names
            los_col = None
            for col in ["los_0", "los", "LOS", "level_of_service"]:
                if col in aadt.columns:
                    los_col = col
                    break
            
            if los_col:
                aadt["cong_value"] = aadt[los_col].map(los_mapping).fillna(0)
            else:
                aadt["cong_value"] = 0
            
            # Create buffer and intersect
            projects["buffer"] = projects.geometry.buffer(402.336)  # 0.25 miles
            intersected = gpd.overlay(aadt, gpd.GeoDataFrame(geometry=projects["buffer"]), how="intersection")
            
            # Sum congestion values
            project_cong = intersected.groupby("project_id")["cong_value"].sum().reset_index(name="sum_cong_value")
            projects = projects.merge(project_cong, on="project_id", how="left")
            projects["sum_cong_value"] = projects["sum_cong_value"].fillna(0)
            
            # Normalize
            max_cong = projects["sum_cong_value"].max() if projects["sum_cong_value"].max() > 0 else 1
            normalized = (projects["sum_cong_value"] / max_cong) * 5
            projects["cong_los"] = normalized.where(normalized % 1 == 0, 0)
            
            return projects[['project_id', 'cong_los']]
            
        except Exception as e:
            print(f"Error in congestion LOS calculation: {e}")
            return pd.DataFrame({
                'project_id': self.projects_gdf['project_id'],
                'cong_los': [0] * len(self.projects_gdf)
            })
    
    def calculate_access_to_jobs(self) -> pd.DataFrame:
        """Calculate access to jobs score"""
        try:
            fc_distances_miles = {"PA": 10, "MA": 7.5, "MC": 5}
            mile_to_meter = 1609.34
            fc_distances_m = {k: v * mile_to_meter for k, v in fc_distances_miles.items()}
            
            projects = self.projects_gdf.to_crs(epsg=2283)
            pop_emp_df = self.pop_emp_gdf.to_crs(epsg=2283)
            pop_emp_df["centroid"] = pop_emp_df.geometry.centroid
            
            results = []
            
            for _, proj in projects.iterrows():
                fc = proj.get("fc", "MA")  # Default to MA if fc not found
                buffer_dist = fc_distances_m.get(fc, fc_distances_m["MA"])
                
                proj_buffer = proj.geometry.buffer(buffer_dist)
                selected = pop_emp_df[pop_emp_df["centroid"].within(proj_buffer)]
                
                # Handle different employment column names
                emp17_col = next((col for col in ["emp17", "emp_17", "employment_2017", "emp2017"] if col in selected.columns), None)
                emp50_col = next((col for col in ["emp50", "emp_50", "employment_2050", "emp2050"] if col in selected.columns), None)
                
                if emp17_col and emp50_col:
                    sum_emp17 = selected[emp17_col].sum()
                    sum_emp50 = selected[emp50_col].sum()
                    pct_change = ((sum_emp50 - sum_emp17) / sum_emp17 * 100) if sum_emp17 != 0 else 0
                else:
                    pct_change = 0
                
                results.append({
                    "project_id": proj["project_id"],
                    "pct_change": pct_change
                })
            
            results_df = pd.DataFrame(results)
            max_change = results_df["pct_change"].max() if results_df["pct_change"].max() > 0 else 1
            results_df["jobs_pc"] = (results_df["pct_change"] / max_change) * 5
            
            return results_df[['project_id', 'jobs_pc']]
            
        except Exception as e:
            print(f"Error in access to jobs calculation: {e}")
            return pd.DataFrame({
                'project_id': self.projects_gdf['project_id'],
                'jobs_pc': [0] * len(self.projects_gdf)
            })
    
    def calculate_access_to_jobs_ej(self) -> pd.DataFrame:
        """Calculate access to jobs in EJ areas score"""
        try:
            fc_distances_miles = {"PA": 10, "MA": 7.5, "MC": 5}
            mile_to_meter = 1609.34
            fc_distances_m = {k: v * mile_to_meter for k, v in fc_distances_miles.items()}
            
            projects = self.projects_gdf.to_crs(epsg=2283)
            pop_emp_df = self.pop_emp_gdf.to_crs(epsg=2283)
            ej = self.ej_gdf.to_crs(epsg=2283)
            
            results = []
            
            for _, proj in projects.iterrows():
                fc = proj.get("fc", "MA")
                buffer_dist = fc_distances_m.get(fc, fc_distances_m["MA"])
                
                proj_buffer = proj.geometry.buffer(buffer_dist)
                ej_clip = ej[ej.intersects(proj_buffer)]
                
                if ej_clip.empty:
                    pct_change = 0
                else:
                    taz_ej_intersect = gpd.overlay(pop_emp_df, ej_clip, how="intersection")
                    
                    emp17_col = next((col for col in ["emp17", "emp_17", "employment_2017"] if col in taz_ej_intersect.columns), None)
                    emp50_col = next((col for col in ["emp50", "emp_50", "employment_2050"] if col in taz_ej_intersect.columns), None)
                    
                    if emp17_col and emp50_col:
                        sum_emp17 = taz_ej_intersect[emp17_col].sum()
                        sum_emp50 = taz_ej_intersect[emp50_col].sum()
                        pct_change = ((sum_emp50 - sum_emp17) / sum_emp17 * 100) if sum_emp17 != 0 else 0
                    else:
                        pct_change = 0
                
                results.append({
                    "project_id": proj["project_id"],
                    "pct_change": pct_change
                })
            
            results_df = pd.DataFrame(results)
            max_change = results_df["pct_change"].max() if results_df["pct_change"].max() > 0 else 1
            results_df["jobs_pc_ej"] = (results_df["pct_change"] / max_change) * 5
            
            return results_df[['project_id', 'jobs_pc_ej']]
            
        except Exception as e:
            print(f"Error in access to jobs EJ calculation: {e}")
            return pd.DataFrame({
                'project_id': self.projects_gdf['project_id'],
                'jobs_pc_ej': [0] * len(self.projects_gdf)
            })
    
    def calculate_access_to_nw(self) -> pd.DataFrame:
        """Calculate access to non-work destinations score"""
        try:
            fc_distances_miles = {"PA": 10, "MA": 7.5, "MC": 5}
            mile_to_meter = 1609.34
            fc_distances_m = {k: v * mile_to_meter for k, v in fc_distances_miles.items()}
            
            projects = self.projects_gdf.to_crs(epsg=2283)
            nw = self.nw_gdf.to_crs(epsg=2283)
            pop_emp_df = self.pop_emp_gdf.to_crs(epsg=2283)
            
            results = []
            
            for _, proj in projects.iterrows():
                fc = proj.get("fc", "MA")
                buffer_dist = fc_distances_m.get(fc, fc_distances_m["MA"])
                
                proj_buffer = proj.geometry.buffer(buffer_dist)
                nw_count = nw[nw.within(proj_buffer)].shape[0]
                taz_selected = pop_emp_df[pop_emp_df.intersects(proj_buffer)]
                
                if taz_selected.empty:
                    density_change = 0
                else:
                    # Get employment and population columns
                    emp17_col = next((col for col in ["emp17", "emp_17", "employment_2017"] if col in taz_selected.columns), None)
                    emp50_col = next((col for col in ["emp50", "emp_50", "employment_2050"] if col in taz_selected.columns), None)
                    pop17_col = next((col for col in ["pop17", "pop_17", "population_2017"] if col in taz_selected.columns), None)
                    pop50_col = next((col for col in ["pop50", "pop_50", "population_2050"] if col in taz_selected.columns), None)
                    
                    sum_emp2017 = taz_selected[emp17_col].sum() if emp17_col else 0
                    sum_emp2050 = taz_selected[emp50_col].sum() if emp50_col else 0
                    sum_pop2017 = taz_selected[pop17_col].sum() if pop17_col else 0
                    sum_pop2050 = taz_selected[pop50_col].sum() if pop50_col else 0
                    
                    area_sqmi = taz_selected.to_crs(epsg=3857).geometry.area.sum() / (1609.34**2)
                    
                    if area_sqmi > 0:
                        pop_emp_den_2017 = nw_count * (sum_emp2017 + sum_pop2017) / area_sqmi
                        pop_emp_den_2050 = nw_count * (sum_emp2050 + sum_pop2050) / area_sqmi
                        density_change = ((pop_emp_den_2050 - pop_emp_den_2017) / pop_emp_den_2017 * 100) if pop_emp_den_2017 != 0 else 0
                    else:
                        density_change = 0
                
                results.append({
                    "project_id": proj["project_id"],
                    "access_nw_pct": density_change
                })
            
            results_df = pd.DataFrame(results)
            max_pct = results_df["access_nw_pct"].max() if results_df["access_nw_pct"].max() > 0 else 1
            results_df["access_nw_norm"] = (results_df["access_nw_pct"] / max_pct) * 5
            
            return results_df[['project_id', 'access_nw_norm']]
            
        except Exception as e:
            print(f"Error in access to non-work destinations calculation: {e}")
            return pd.DataFrame({
                'project_id': self.projects_gdf['project_id'],
                'access_nw_norm': [0] * len(self.projects_gdf)
            })
    
    def calculate_access_to_nw_ej(self) -> pd.DataFrame:
        """Calculate access to non-work destinations in EJ areas score"""
        try:
            fc_distances_miles = {"PA": 10, "MA": 7.5, "MC": 5}
            mile_to_meter = 1609.34
            fc_distances_m = {k: v * mile_to_meter for k, v in fc_distances_miles.items()}
            
            projects = self.projects_gdf.to_crs(epsg=2283)
            nw = self.nw_gdf.to_crs(epsg=2283)
            pop_emp_df = self.pop_emp_gdf.to_crs(epsg=2283)
            ej = self.ej_gdf.to_crs(epsg=2283)
            
            results = []
            
            for _, proj in projects.iterrows():
                fc = proj.get("fc", "MA")
                buffer_dist = fc_distances_m.get(fc, fc_distances_m["MA"])
                
                proj_buffer = proj.geometry.buffer(buffer_dist)
                
                try:
                    ej_union = ej.union_all() if hasattr(ej, 'union_all') else ej.unary_union
                    nw_count = nw[nw.within(proj_buffer) & nw.within(ej_union)].shape[0]
                    taz_selected = pop_emp_df[pop_emp_df.intersects(proj_buffer) & pop_emp_df.intersects(ej_union)]
                except:
                    nw_count = 0
                    taz_selected = gpd.GeoDataFrame()
                
                if taz_selected.empty:
                    density_change = 0
                else:
                    # Similar calculation as non-EJ version
                    emp17_col = next((col for col in ["emp17", "emp_17", "employment_2017"] if col in taz_selected.columns), None)
                    emp50_col = next((col for col in ["emp50", "emp_50", "employment_2050"] if col in taz_selected.columns), None)
                    pop17_col = next((col for col in ["pop17", "pop_17", "population_2017"] if col in taz_selected.columns), None)
                    pop50_col = next((col for col in ["pop50", "pop_50", "population_2050"] if col in taz_selected.columns), None)
                    
                    sum_emp2017 = taz_selected[emp17_col].sum() if emp17_col else 0
                    sum_emp2050 = taz_selected[emp50_col].sum() if emp50_col else 0
                    sum_pop2017 = taz_selected[pop17_col].sum() if pop17_col else 0
                    sum_pop2050 = taz_selected[pop50_col].sum() if pop50_col else 0
                    
                    area_sqmi = taz_selected.to_crs(epsg=3857).geometry.area.sum() / (1609.34**2)
                    
                    if area_sqmi > 0:
                        pop_emp_den_2017 = nw_count * (sum_emp2017 + sum_pop2017) / area_sqmi
                        pop_emp_den_2050 = nw_count * (sum_emp2050 + sum_pop2050) / area_sqmi
                        density_change = ((pop_emp_den_2050 - pop_emp_den_2017) / pop_emp_den_2017 * 100) if pop_emp_den_2017 != 0 else 0
                    else:
                        density_change = 0
                
                results.append({
                    "project_id": proj["project_id"],
                    "access_nw_pct": density_change
                })
            
            results_df = pd.DataFrame(results)
            max_pct = results_df["access_nw_pct"].max() if results_df["access_nw_pct"].max() > 0 else 1
            results_df["access_nw_ej_norm"] = (results_df["access_nw_pct"] / max_pct) * 5
            
            return results_df[['project_id', 'access_nw_ej_norm']]
            
        except Exception as e:
            print(f"Error in access to non-work destinations EJ calculation: {e}")
            return pd.DataFrame({
                'project_id': self.projects_gdf['project_id'],
                'access_nw_ej_norm': [0] * len(self.projects_gdf)
            })
    
    def calculate_final_scores(self) -> Dict[str, Any]:
        """Calculate all scores and final ranking"""
        try:
            # Calculate all individual scores
            safety_freq = self.calculate_safety_frequency()
            safety_rate = self.calculate_safety_rate(safety_freq)
            cong_demand = self.calculate_congestion_demand()
            cong_los = self.calculate_congestion_los()
            eq_acc_jobs = self.calculate_access_to_jobs()
            eq_acc_jobs_ej = self.calculate_access_to_jobs_ej()
            eq_acc_nw = self.calculate_access_to_nw()
            eq_acc_nw_ej = self.calculate_access_to_nw_ej()
            
            # Merge all scores
            dfs = [safety_freq, safety_rate, cong_demand, cong_los, 
                   eq_acc_jobs, eq_acc_jobs_ej, eq_acc_nw, eq_acc_nw_ej]
            
            merged_data = reduce(lambda left, right: pd.merge(left, right, on="project_id", how="outer"), dfs)
            
            # Merge with original project data
            final_gdf = self.projects_gdf.merge(merged_data, on="project_id", how="left")
            
            # Fill NaN values with 0
            score_columns = ['safety_freq', 'safety_rate', 'cong_demand', 'cong_los', 
                           'jobs_pc', 'jobs_pc_ej', 'access_nw_norm', 'access_nw_ej_norm']
            final_gdf[score_columns] = final_gdf[score_columns].fillna(0)
            
            # Drop 'bcr' column if it exists
            if 'bcr' in final_gdf.columns:
                final_gdf = final_gdf.drop(columns=['bcr'])
            
            # Calculate total benefit
            final_gdf['benefit'] = final_gdf[score_columns].sum(axis=1)
            
            # Calculate rank
            final_gdf['rank'] = final_gdf['benefit'].rank(ascending=False, method='dense').astype(int)
            
            # Convert to serializable format
            results = []
            for _, row in final_gdf.iterrows():
                project_result = {
                    'project_id': int(row['project_id']),
                    'type': str(row.get('type', 'Unknown')),
                    'county': str(row.get('county', 'Unknown')),
                    'safety_freq': float(row.get('safety_freq', 0)),
                    'safety_rate': float(row.get('safety_rate', 0)),
                    'cong_demand': float(row.get('cong_demand', 0)),
                    'cong_los': float(row.get('cong_los', 0)),
                    'jobs_pc': float(row.get('jobs_pc', 0)),
                    'jobs_pc_ej': float(row.get('jobs_pc_ej', 0)),
                    'access_nw_norm': float(row.get('access_nw_norm', 0)),
                    'access_nw_ej_norm': float(row.get('access_nw_ej_norm', 0)),
                    'benefit': float(row.get('benefit', 0)),
                    'cost_mil': float(row.get(cost_col, 1)) if cost_col else 1.0,
                    'rank': int(row.get('rank', 999))
                }
                results.append(project_result)
            
            # Sort by rank
            results_sorted = sorted(results, key=lambda x: x['rank'])

            summary = {
                "total_projects": len(results_sorted),
                "total_cost": sum(p['cost_mil'] for p in results_sorted)
            }

            return {"projects": results_sorted, "summary": summary}

        except Exception as e:
            print(f"Error in final score calculation: {e}")
            return {
                "projects": [],
                "summary": {"error": str(e)}
            }

@app.get("/")
def read_root():
    return {"message": "Welcome to the STBG Project Prioritization API"}


@app.options("/analyze")
async def analyze_options():
    return JSONResponse(content={"message": "OK"})

@app.post("/analyze", response_model=AnalysisResults)
async def analyze_projects(
    projects_file: UploadFile = File(...),
    crashes_file: UploadFile = File(...),
    aadt_file: UploadFile = File(...),
    pop_emp_file: UploadFile = File(...),
    ej_areas_file: UploadFile = File(...),
    non_work_dest_file: UploadFile = File(...),
):
    
    with tempfile.TemporaryDirectory() as temp_dir:
        files_dict = {}
        try:
            # Create a mapping of official keys to expected file name parts
            file_key_map = {
                "projects": "project",
                "crashes": "crash",
                "aadt": "aadt",
                "pop_emp": ["pop", "emp"],
                "ej_areas": "ej",
                "non_work_dest": "non_work"
            }

            # Create a reverse map for easy lookup
            reverse_file_key_map = {}
            for key, parts in file_key_map.items():
                if isinstance(parts, list):
                    for part in parts:
                        reverse_file_key_map[part] = key
                else:
                    reverse_file_key_map[parts] = key

            all_files = [
                projects_file, crashes_file, aadt_file, 
                pop_emp_file, ej_areas_file, non_work_dest_file
            ]

            for upload_file in all_files:
                file_path = os.path.join(temp_dir, upload_file.filename)
                with open(file_path, "wb") as f:
                    f.write(await upload_file.read())
                
                # Find the corresponding key
                file_key = None
                for part, key in reverse_file_key_map.items():
                    if part in upload_file.filename.lower():
                        file_key = key
                        break
                
                if file_key:
                    files_dict[file_key] = file_path

            analyzer = STBGAnalyzer()
            analyzer.load_geospatial_data(files_dict)
            
            results = analyzer.calculate_final_scores()
            
            if "error" in results.get("summary", {}):
                raise HTTPException(status_code=500, detail=results["summary"]["error"])
                
            response = JSONResponse(content=results)
            return response

        except HTTPException as he:
            raise he
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)