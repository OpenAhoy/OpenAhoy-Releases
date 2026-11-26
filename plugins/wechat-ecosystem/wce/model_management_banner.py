"""Current model highlight for the Settings tile."""

# Change this line when a different set of supported models is featured.
FEATURED = 'Seedance 2.5、MiniMax H3 与 OpenAI 动图'

HTML = '''<button id="wbModelsLink" class="wb-model-banner" data-wb-route="models" type="button"
 aria-controls="wbModels" aria-labelledby="wbModelBannerTitle" aria-describedby="wbModelBannerFeature">
 <span class="wb-model-banner-copy">
  <svg class="wb-model-banner-mark" viewBox="0 0 32 32" width="32" height="32" aria-hidden="true">
   <rect x="3" y="4" width="14" height="14" rx="4"/><rect x="20" y="4" width="9" height="9" rx="3"/>
   <rect x="20" y="16" width="9" height="12" rx="3"/><rect x="3" y="21" width="14" height="7" rx="3"/>
  </svg>
  <span id="wbModelBannerTitle">模型管理</span>
  <span id="wbModelBannerFeature">''' + FEATURED + '''</span>
  <span class="wb-model-banner-action">
   <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M5 12h13m-5-5 5 5-5 5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
  </span>
 </span>
</button>'''
