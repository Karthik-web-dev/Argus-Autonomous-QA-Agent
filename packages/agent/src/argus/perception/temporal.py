from playwright.async_api import Page


async def capture_animations(page: Page) -> list[dict]:
    return await page.evaluate("""() => document.getAnimations().map(a => ({
      playState: a.playState, currentTime: a.currentTime,
      target: a.effect?.target?.tagName?.toLowerCase() || null
    }))""")


async def install_mutation_observer(page: Page) -> None:
    await page.add_init_script("""() => {
      window.__argusMutations = [];
      new MutationObserver(records => window.__argusMutations.push(...records.map(r => ({
        type: r.type, target: r.target.nodeName, attribute: r.attributeName || null
      })))).observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
    }""")
