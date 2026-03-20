def search(query, apps):
    if not query:
        return apps
    
    results = []
    query = query.lower()
    
    for app in apps:
        name = app.get('Name', '').lower()
        # Basic scoring: 100 for exact start, 50 for contains
        score = 0
        if name.startswith(query):
            score = 100
        elif query in name:
            score = 50
            
        if score > 0:
            # We store the score inside a copy of the dict so the UI can read it
            app_with_score = app.copy()
            app_with_score['score'] = score
            results.append(app_with_score)
    
    # Sort by score (highest first)
    results.sort(key=lambda x: x.get('score', 0), reverse=True)
    return results