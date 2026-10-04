import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { language, setLanguage, startTranslation, translate } from '../src/i18n'
import LocalizedDateInput from '../src/components/LocalizedDateInput.vue'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { parse as parseSfc } from '@vue/compiler-sfc'
import { parse as parseTemplate, type TemplateChildNode } from '@vue/compiler-dom'

let stop: (() => void) | undefined
afterEach(() => { stop?.(); stop = undefined; document.body.innerHTML = ''; setLanguage('zh') })

describe('language changes', () => {
  it('covers static interface text on every Vue page and keeps option values explicit', () => {
    language.value = 'en'
    const failures: string[] = []
    const inspect = (node: TemplateChildNode, file: string) => {
      if (node.type === 1) {
        if (node.props.some(p => p.type === 6 && p.name === 'data-no-translate')) return
        if (node.tag === 'option' && node.children.some(c => c.type === 2 && /[\u3400-\u9fff]/.test(c.content))) {
          if (!node.props.some(p => (p.type === 6 && p.name === 'value') || (p.type === 7 && p.name === 'bind' && p.arg?.type === 4 && p.arg.content === 'value'))) failures.push(`${file}: option missing value`)
        }
        for (const child of node.children) inspect(child, file)
      } else if (node.type === 2 && /[\u3400-\u9fff]/.test(translate(node.content))) {
        failures.push(`${file}: ${node.content.trim()}`)
      }
    }
    const visit = (folder: string) => {
      for (const file of readdirSync(folder, { withFileTypes: true })) {
        const path = resolve(folder, file.name)
        if (file.isDirectory()) visit(path)
        else if (file.name.endsWith('.vue')) {
          const template = parseSfc(readFileSync(path, 'utf8')).descriptor.template
          if (template) for (const node of parseTemplate(template.content).children) inspect(node, file.name)
        }
      }
    }
    visit(resolve(import.meta.dirname, '../src'))
    expect(failures).toEqual([])
  })
  it('translates complete notices, statuses and department labels', () => {
    language.value = 'en'
    expect(translate('总部账号：门店业务仅供查看')).toBe('Headquarters account: store operations are read-only')
    expect(translate('待签收')).toBe('Awaiting receipt')
    expect(translate('鮮魚部')).toBe('Seafood')
    expect(translate('性别 *')).toBe('Gender *')
  })
  it('restores source text through repeated switches and translates newly rendered content', async () => {
    document.body.innerHTML = '<p>总部账号：门店业务仅供查看</p><strong data-no-translate>总部供应商 MarketFlow</strong><select><option value="在职">在职</option></select>'
    stop = startTranslation()
    for (const locale of ['en', 'ja', 'zh', 'en'] as const) {
      setLanguage(locale)
      expect(document.querySelector('p')?.textContent).toBe(translate('总部账号：门店业务仅供查看'))
      expect(document.querySelector('strong')?.textContent).toBe('总部供应商 MarketFlow')
      expect(document.querySelector('select')?.value).toBe('在职')
    }
    const message = document.createElement('p')
    message.textContent = '待签收'
    document.body.append(message)
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(message.textContent).toBe('Awaiting receipt')
  })
  it('reacts to backend field updates without reusing old translated values', async () => {
    document.body.innerHTML = '<p>待签收</p>'
    stop = startTranslation()
    setLanguage('en')
    document.querySelector('p')!.firstChild!.nodeValue = '已签收'
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(document.querySelector('p')?.textContent).toBe('Received')
    setLanguage('ja')
    expect(document.querySelector('p')?.textContent).toBe('入荷済み')
  })
})

describe('localized date input', () => {
  it('changes display locale while retaining the ISO form value and date constraints', async () => {
    setLanguage('en')
    const wrapper = mount(LocalizedDateInput, { props: { modelValue: '2026-10-04' }, attrs: { min: '2026-01-01', required: true } })
    expect(wrapper.find('.locale-date-caption').text()).toBe('10/04/2026')
    expect(wrapper.find('input').element.value).toBe('2026-10-04')
    expect(wrapper.find('input').attributes('min')).toBe('2026-01-01')
    setLanguage('ja'); await nextTick()
    expect(wrapper.find('.locale-date-caption').text()).toBe('2026/10/04')
    await wrapper.find('input').setValue('2026-11-03')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['2026-11-03'])
    wrapper.unmount()
  })
})
