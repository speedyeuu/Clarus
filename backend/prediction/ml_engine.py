import os
import joblib
import pandas as pd
from loguru import logger
from typing import Optional, Dict
from db.client import get_supabase
from sklearn.ensemble import HistGradientBoostingRegressor

MODEL_PATH = os.path.join(os.path.dirname(__file__), "ml", "hgb_model.joblib")
MIN_TRAIN_SAMPLES = 500  # Pro XGBoost potřebujeme alespoň stovky řádků, aby nedošlo k overfittu

def load_data_for_training() -> pd.DataFrame:
    """Stáhne historická data z DB pro trénink XGBoost."""
    db = get_supabase()
    res = db.table("daily_scores").select("*").order("date", desc=False).execute()
    
    if not res.data:
        return pd.DataFrame()
        
    df = pd.DataFrame(res.data)
    # Potřebujeme vytvořit cílovou proměnnou (target): změnu skóre za 7 dní
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(by=['pair', 'date'])
    
    # 7-day future score
    df['future_score_7d'] = df.groupby('pair')['total_score'].shift(-7)
    df['target_delta'] = df['future_score_7d'] - df['total_score']
    
    df = df.dropna(subset=['target_delta'])
    return df

def train_xgboost_model() -> bool:
    """
    Natrénuje XGBoost Regressor na predikci 7-denní delty skóre na základě
    historických složek fundamentu a volatility.
    """
    logger.info("Stahuji data pro trénink ML vrstvy...")
    df = load_data_for_training()
    
    if len(df) < MIN_TRAIN_SAMPLES:
        logger.warning(f"[ML Engine] Nedostatek dat pro trénink (máme {len(df)}, potřebujeme {MIN_TRAIN_SAMPLES}). Učení odloženo.")
        return False
        
    # Feature engineering
    features = [
        'score_interest_rates', 'score_inflation', 'score_gdp', 
        'score_labor', 'score_cot', 'score_spmi', 'score_retail_sales',
        'score_trend', 'score_retail_sentiment', 'score_seasonality'
    ]
    
    X = df[features].fillna(0)
    y = df['target_delta']
    
    # Trénink modelu (HistGradientBoosting je ekvivalent LightGBM/XGBoost bez instalace C++ dependencies)
    model = HistGradientBoostingRegressor(
        max_iter=100,
        max_depth=3,
        learning_rate=0.05,
        random_state=42
    )
    
    logger.info("Trénuji ML model...")
    model.fit(X, y)
    
    # Uložení modelu
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    logger.info(f"Model ML vrstvy úspěšně natrénován a uložen do {MODEL_PATH}.")
    return True

def predict_xgboost_delta(current_scores: Dict[str, float]) -> Optional[float]:
    """
    Pokud existuje natrénovaný model, odhadne 7-denní změnu skóre.
    """
    if not os.path.exists(MODEL_PATH):
        return None
        
    try:
        model = joblib.load(MODEL_PATH)
        features = [
            'score_interest_rates', 'score_inflation', 'score_gdp', 
            'score_labor', 'score_cot', 'score_spmi', 'score_retail_sales',
            'score_trend', 'score_retail_sentiment', 'score_seasonality'
        ]
        
        # Zajištění stejného pořadí jako při tréninku
        X_pred = pd.DataFrame([{f: current_scores.get(f, 0.0) for f in features}])
        
        pred_delta = float(model.predict(X_pred)[0])
        logger.info(f"[ML Engine] Nelineární ML vrstva predikuje 7-day delta: {pred_delta:+.4f}")
        return pred_delta
    except Exception as e:
        logger.error(f"[ML Engine] Chyba při inferenci ML modelu: {e}")
        return None
