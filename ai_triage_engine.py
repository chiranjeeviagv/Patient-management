import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.ensemble import RandomForestClassifier

# 1. Clinical Knowledge Base for Symptom-to-Specialty Triage (20+ Specialties)
SPECIALTY_CORPUS = {
    "Cardiology": "chest pain palpitations shortness of breath high blood pressure hypertension heart rate dizziness swelling legs",
    "Neurology": "severe headache migraine seizure numbness tingling memory loss stroke vertigo tremors blurred vision",
    "Orthopedics": "joint pain fracture back pain knee swelling arthritis sprain shoulder stiffness bone injury",
    "Dermatology": "skin rash itching acne eczema hair loss fungal infection mole discoloration hives",
    "Pediatrics": "child fever infant cough vaccination growth ear pain pediatric cold vomiting",
    "Gastroenterology": "abdominal pain acidity reflux nausea vomiting diarrhea constipation liver jaundice bloating",
    "Pulmonology": "chronic cough asthma wheezing bronchitis breathing difficulty pneumonia chest congestion",
    "ENT (Otolaryngology)": "sore throat earache sinusitis hearing loss nasal congestion tonsillitis snoring",
    "Ophthalmology": "eye pain redness blurry vision cataract glaucoma watery eyes sensitivity to light",
    "Endocrinology": "diabetes thyroid fatigue weight gain hormonal imbalance excessive thirst high sugar",
    "Nephrology": "kidney pain urinary infection swelling ankles dialysis creatinine blood in urine",
    "Urology": "kidney stones painful urination prostate bladder control urinary frequency",
    "Gynecology & Obstetrics": "pregnancy prenatal pelvic pain menstrual irregularity pcos menopause",
    "Psychiatry": "anxiety depression insomnia panic attacks stress mood swings trauma",
    "Oncology": "lump unexplained weight loss biopsy tumor chemotherapy fatigue",
    "General Medicine": "viral fever body ache weakness routine checkup infection cold flu",
    "Dental & Maxillofacial": "toothache gum bleeding jaw pain cavity wisdom tooth root canal",
    "Rheumatology": "autoimmune lupus joint stiffness chronic inflammation fibromyalgia",
    "Hematology": "anemia low hemoglobin bleeding disorder clotting bruising fatigue",
    "Emergency & Critical Care": "unconscious severe bleeding trauma accident acute chest pain anaphylaxis"
}

class ClinicalAIEngine:
    def __init__(self):
        # Train TF-IDF Vectorizer on clinical symptom corpus
        self.specialties = list(SPECIALTY_CORPUS.keys())
        self.corpus = list(SPECIALTY_CORPUS.values())
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.tfidf_matrix = self.vectorizer.fit_transform(self.corpus)

        # Train Random Forest Classifier for Appointment No-Show Risk
        self.noshow_model = self._train_noshow_model()

    def recommend_specialty(self, symptom_text: str, top_k: int = 3):
        """Maps free-text patient symptoms to ranked clinical specialties."""
        if not symptom_text or not symptom_text.strip():
            return [("General Medicine", 0.0, "Routine")]

        query_vec = self.vectorizer.transform([symptom_text.lower()])
        similarities = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
        top_indices = similarities.argsort()[::-1][:top_k]

        # Determine Triage Urgency Level
        urgent_keywords = {"chest pain", "unconscious", "bleeding", "stroke", "seizure", "breathing", "trauma"}
        is_urgent = any(kw in symptom_text.lower() for kw in urgent_keywords)
        urgency = "🔴 High / Urgent" if is_urgent else "🟢 Standard Outpatient"

        results = []
        for idx in top_indices:
            score = round(float(similarities[idx]) * 100, 1)
            if score > 0:
                results.append((self.specialties[idx], score, urgency))

        if not results:
            results.append(("General Medicine", 15.0, urgency))
        return results

    def _train_noshow_model(self):
        """Trains a lightweight Random Forest model on historical appointment features."""
        rng = np.random.default_rng(42)
        n_samples = 400
        # Features: [age, lead_days, is_evening_shift (0=Morning 9-2, 1=Evening 3-9), prior_misses, distance_km]
        age = rng.integers(18, 80, n_samples)
        lead_days = rng.integers(0, 30, n_samples)
        evening_shift = rng.integers(0, 2, n_samples)
        prior_misses = rng.integers(0, 4, n_samples)
        distance_km = rng.integers(1, 50, n_samples)

        X = np.column_stack([age, lead_days, evening_shift, prior_misses, distance_km])
        # Synthetic risk probability grounded in healthcare scheduling patterns
        risk_score = (lead_days * 0.02) + (prior_misses * 0.22) + (distance_km * 0.005) - (age * 0.002)
        y = (risk_score > 0.45).astype(int)

        clf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
        clf.fit(X, y)
        return clf

    def predict_noshow_risk(self, age: int, lead_days: int, shift_slot: str, prior_misses: int = 0, distance_km: int = 8):
        """Returns probability (%) of patient missing the appointment."""
        is_evening = 1 if "3:00 PM" in shift_slot or "Evening" in shift_slot else 0
        features = np.array([[age, lead_days, is_evening, prior_misses, distance_km]])
        prob = self.noshow_model.predict_proba(features)[0][1] * 100
        label = "High Risk (Send SMS Reminder)" if prob >= 55 else ("Moderate Risk" if prob >= 30 else "Low Risk")
        return round(prob, 1), label
