#!/usr/bin/env python3
"""
Demo script: Run Istina with MockProvider

This script demonstrates how to:
1. Set ISTINA_PROVIDER=mock
2. Ingest articles from RSS feeds  
3. Analyze them using MockProvider
4. Review the bias analysis results

Run from project root:
    python demo_mock_provider.py

Or with explicit environment variable:
    ISTINA_PROVIDER=mock python demo_mock_provider.py
"""

import os
import sys
from typing import List

# Ensure src is on the path
sys.path.insert(0, "src")

# Set mock provider (can also be set via environment)
os.environ.setdefault("ISTINA_PROVIDER", "mock")

# Imports
from istina.config.settings import load_settings, validate_settings
from istina.model.providers.provider_factory import create_provider
from istina.model.repositories.memory_repository import MemoryRepository
from istina.controller.services.ingest_service import IngestService
from istina.controller.services.analysis_service import AnalysisService, SelectionParams
from istina.utils.logger import configure_logger


def print_banner(title: str):
    """Print a section banner."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")


def print_article_summary(articles: List):
    """Print a summary of ingested articles.""" 
    print(f"Total articles ingested: {len(articles)}")
    
    if articles:
        print("\nSample articles:")
        for i, article in enumerate(articles[:3], 1):
            print(f"  [{i}] {article.title}")
            print(f"      Source: {article.source}")
            print(f"      URL: {article.url}")
            print(f"      Published: {article.published_at}")
            print(f"      ID: {article.id[:12]}...")
            print()


def print_analysis_results(repo: MemoryRepository):
    """Print bias score analysis results."""
    # Get all articles and check for bias scores
    articles = repo.list_articles()
    bias_scores = []
    
    for article in articles:
        score = repo.get_bias_score(article.id)
        if score:
            bias_scores.append(score)
    
    print(f"Total articles analyzed: {len(bias_scores)}")
    
    if bias_scores:
        print("\nBias Analysis Results:")
        print(f"{'Article':<40} {'Bias Label':<12} {'Confidence':<10} {'Flags'}")
        print("-" * 80)
        
        for score in bias_scores:
            # Get article for reference
            article = repo.get_article(score.article_id) 
            title = article.title[:35] + "..." if len(article.title) > 35 else article.title
            flags = ", ".join(score.rhetorical_bias[:2])  # Show first 2 flags
            if len(score.rhetorical_bias) > 2:
                flags += f" +{len(score.rhetorical_bias)-2} more"
                
            print(f"{title:<40} {score.overall_bias_label:<12} {score.confidence:<10.2f} {flags}")
        
        print(f"\nSample detailed analysis:")
        sample_score = bias_scores[0]
        sample_article = repo.get_article(sample_score.article_id)
        
        print(f"Article: {sample_article.title}")
        print(f"Overall Bias: {sample_score.overall_bias_label} (confidence: {sample_score.confidence:.2f})")
        print(f"Rhetorical Flags: {sample_score.rhetorical_bias}")
        print(f"Claims Found: {len(sample_score.claim_checks)}")
        if sample_score.claim_checks:
            claim = sample_score.claim_checks[0]
            print(f"  Sample claim: '{claim['claim']}'")
            print(f"  Verdict: {claim['verdict']} (confidence: {claim['confidence']})")
        print(f"Provider: {sample_score.provider}")
        print(f"Timestamp: {sample_score.timestamp}")


def main():
    """Main demo function."""
    
    print_banner("Istina Demo with Mock Provider")
    
    # 1. Load configuration
    print("Loading configuration...")
    settings = load_settings()
    validate_settings(settings)
    
    print(f"Environment: {settings.env}")
    print(f"Provider: {settings.provider}")
    print(f"Repository: {settings.repo_type}")
    print(f"Log Level: {settings.log_level}")
    
    # 2. Setup logging
    logger = configure_logger(settings)
    
    # 3. Create provider via factory  
    print_banner("Creating Provider")
    provider = create_provider(settings)
    print(f"Provider created: {type(provider).__name__}")
    print(f"Provider name: {provider.provider_name}")
    
    # 4. Create repository and services
    print_banner("Setting up Services")
    repository = MemoryRepository()
    ingest_service = IngestService(repository)
    analysis_service = AnalysisService(repository)
    
    print("Services initialized:")
    print(f"  Repository: {type(repository).__name__}")
    print(f"  Ingest Service: {type(ingest_service).__name__}")
    print(f"  Analysis Service: {type(analysis_service).__name__}")
    print(f"  Provider: {type(provider).__name__} (will be passed to analysis)")
    # Use a few reliable news feeds
    feeds = [
        "http://feeds.bbci.co.uk/news/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        # You can add more feeds here
    ]
    
    print(f"Fetching from {len(feeds)} RSS feeds...")
    try:
        ingest_result = ingest_service.ingest(feeds)
        
        print(f"Ingest completed:")
        print(f"  Articles fetched: {ingest_result.fetched_count}")
        print(f"  New articles: {ingest_result.new_count}")
        print(f"  Existing articles: {ingest_result.existing_count}")
        
        if ingest_result.errors:
            print(f"  Errors: {len(ingest_result.errors)}")
            for error in ingest_result.errors[:3]:  # Show first 3 errors
                print(f"    - {error}")
        
        # Show article summary
        articles = repository.list_articles()
        print_article_summary(articles)
        
    except Exception as e:
        print(f"Ingest failed: {e}")
        print("Continuing with demo using mock articles...")
        
        # Create some mock articles for demonstration
        from istina.model.entities.article import Article
        
        mock_articles = [
            Article.create(
                title="Breaking: Shocking revelation about political scandal",
                url="https://example.com/scandal",
                source="Demo News",
                published_at="2024-01-15T12:00:00Z",
                summary="Everyone knows this clearly represents a major political development."
            ),
            Article.create(
                title="Simple weather forecast for tomorrow",
                url="https://example.com/weather",
                source="Weather Service", 
                published_at="2024-01-15T13:00:00Z",
                summary="Partly cloudy with moderate temperatures expected."
            ),
            Article.create(
                title="Elite mainstream media explodes with outrage over new policy",
                url="https://example.com/media-outrage",
                source="Political Observer",
                published_at="2024-01-15T14:00:00Z", 
                summary="They are obviously trying to undermine the new bombshell legislation."
            )
        ]
        
        for article in mock_articles:
            repository.add_articles([article])
        
        print_article_summary(mock_articles)
    
    # 6. Analyze articles with MockProvider
    print_banner("Analyzing Articles with Mock Provider")
    
    # Select articles for analysis
    selection_params = SelectionParams(limit=10)  # Analyze up to 10 articles
    
    print(f"Running bias analysis...")
    try:
        analysis_result = analysis_service.analyze(provider, selection_params)
        
        print(f"Analysis completed:")
        print(f"  Articles analyzed: {analysis_result.analyzed_count}")
        print(f"  Articles skipped: {analysis_result.skipped_count}")
        print(f"  Analysis failures: {analysis_result.failed_count}")
        
        if analysis_result.errors:
            print(f"  Errors: {len(analysis_result.errors)}")
            for error in analysis_result.errors[:3]:
                print(f"    - {error}")
    
    except Exception as e:
        print(f"Analysis failed: {e}")
        return 1
    
    # 7. Display results
    print_banner("Analysis Results")
    print_analysis_results(repository)
    
    # 8. Test deterministic behavior
    print_banner("Testing Deterministic Behavior")
    
    articles = repository.list_articles()
    if articles:
        test_article = articles[0]
        print(f"Testing deterministic analysis on: {test_article.title[:50]}...")
        
        # Analyze the same article multiple times
        result1 = provider.analyze_article(test_article)
        result2 = provider.analyze_article(test_article)
        
        print(f"Analysis 1 - Bias: {result1.overall_bias_label}, Confidence: {result1.confidence}")
        print(f"Analysis 2 - Bias: {result2.overall_bias_label}, Confidence: {result2.confidence}")
        print(f"Timestamps match: {result1.timestamp == result2.timestamp}")
        print(f"Results identical: {result1.overall_bias_label == result2.overall_bias_label and result1.confidence == result2.confidence}")
        
        if result1.timestamp == result2.timestamp:
            print("✅ MockProvider is deterministic!")
        else:
            print("❌ MockProvider results differ between runs")
    
    print_banner("Demo Complete")
    print("The mock provider is working correctly!")
    print("\nTo run your own analysis:")
    print("1. Set ISTINA_PROVIDER=mock in environment")
    print("2. Use the provider factory: create_provider(settings)")
    print("3. Call provider.analyze_article(article) for deterministic results")
    print("\nFor production: switch to ISTINA_PROVIDER=gemini when ready")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())