import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans


INPUT_FILE = "Dataset/online_retail_II.csv"   


if INPUT_FILE.lower().endswith(".csv"):
    try:
        df = pd.read_csv(INPUT_FILE, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(INPUT_FILE, encoding="ISO-8859-1")
else:
    df = pd.concat(pd.read_excel(INPUT_FILE, sheet_name=None).values(), ignore_index=True)

print("Raw rows:", len(df))

df = df.rename(columns={
    "Invoice": "InvoiceNo",
    "Customer ID": "CustomerID",
    "Price": "UnitPrice",
})


df = df.drop_duplicates()
df = df.dropna(subset=["CustomerID"])
df["InvoiceNo"] = df["InvoiceNo"].astype(str)
df = df[~df["InvoiceNo"].str.startswith("C")]          
df = df[(df["Quantity"] > 0) & (df["UnitPrice"] > 0)]  

non_products = ["POST", "D", "M", "BANK CHARGES", "DOT", "CRUK", "PADS", "AMAZONFEE"]
df = df[~df["StockCode"].astype(str).isin(non_products)]

df["CustomerID"] = df["CustomerID"].astype(int)
df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
df["TotalPrice"] = df["Quantity"] * df["UnitPrice"]

country_fix = {
    "EIRE": "Ireland",
    "RSA": "South Africa",
    "USA": "United States",
    "Channel Islands": "Jersey",
    "West Indies": "Jamaica",
}
df["Country"] = df["Country"].replace(country_fix)
df = df[~df["Country"].isin(["Unspecified", "European Community"])]

print("Clean rows:", len(df), "| Customers:", df["CustomerID"].nunique())


snapshot = df["InvoiceDate"].max() + pd.Timedelta(days=1)

rfm = df.groupby("CustomerID").agg(
    Recency=("InvoiceDate", lambda x: (snapshot - x.max()).days),
    Frequency=("InvoiceNo", "nunique"),
    Monetary=("TotalPrice", "sum"),
    FirstPurchase=("InvoiceDate", "min"),
    LastPurchase=("InvoiceDate", "max"),
).reset_index()

main_country = df.groupby("CustomerID")["Country"].agg(lambda x: x.mode().iat[0])
rfm = rfm.merge(main_country.rename("Country"), on="CustomerID")

rfm["R"] = pd.qcut(rfm["Recency"], 5, labels=[5, 4, 3, 2, 1]).astype(int)
rfm["F"] = pd.qcut(rfm["Frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
rfm["M"] = pd.qcut(rfm["Monetary"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
rfm["RFM_Score"] = rfm["R"].astype(str) + rfm["F"].astype(str) + rfm["M"].astype(str)
rfm["RFM_Total"] = rfm["R"] + rfm["F"] + rfm["M"]

seg_map = {
    r"[1-2][1-2]": "Hibernating",
    r"[1-2][3-4]": "At Risk",
    r"[1-2]5": "Can't Lose Them",
    r"3[1-2]": "About to Sleep",
    r"33": "Need Attention",
    r"[3-4][4-5]": "Loyal Customers",
    r"41": "Promising",
    r"51": "New Customers",
    r"[4-5][2-3]": "Potential Loyalists",
    r"5[4-5]": "Champions",
}
rfm["Segment"] = (rfm["R"].astype(str) + rfm["F"].astype(str)).replace(seg_map, regex=True)

print(rfm["Segment"].value_counts())


X = np.log1p(rfm[["Recency", "Frequency", "Monetary"]])
X = StandardScaler().fit_transform(X)
rfm["KMeans_Cluster"] = KMeans(n_clusters=4, random_state=42, n_init=10).fit_predict(X)

df["InvoiceMonth"] = df["InvoiceDate"].dt.to_period("M")
df["CohortMonth"] = df.groupby("CustomerID")["InvoiceDate"].transform("min").dt.to_period("M")
df["CohortIndex"] = (
    (df["InvoiceMonth"].dt.year - df["CohortMonth"].dt.year) * 12
    + (df["InvoiceMonth"].dt.month - df["CohortMonth"].dt.month)
    + 1
)

cohort = (
    df.groupby(["CohortMonth", "CohortIndex"])
    .agg(Customers=("CustomerID", "nunique"), Revenue=("TotalPrice", "sum"))
    .reset_index()
)
cohort_size = cohort[cohort["CohortIndex"] == 1][["CohortMonth", "Customers"]].rename(
    columns={"Customers": "CohortSize"}
)
cohort = cohort.merge(cohort_size, on="CohortMonth")
cohort["RetentionRate"] = cohort["Customers"] / cohort["CohortSize"]
cohort["CohortMonth"] = cohort["CohortMonth"].dt.to_timestamp()

df = df.merge(rfm[["CustomerID", "Segment"]], on="CustomerID")
df["InvoiceMonth"] = df["InvoiceMonth"].dt.to_timestamp()
df["CohortMonth"] = df["CohortMonth"].dt.to_timestamp()

df.drop(columns=[]).to_csv("clean_transactions.csv", index=False)
rfm.to_csv("rfm_segments.csv", index=False)
cohort.to_csv("cohort_retention.csv", index=False)
print("Done: clean_transactions.csv, rfm_segments.csv, cohort_retention.csv")
