<template>
  <div v-if="video" class="space-y-6">
    <!-- Back button and title -->
    <div class="flex items-center gap-4">
      <RouterLink
        to="/videos"
        class="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface-elevated transition-colors"
      >
        <ArrowLeft class="w-5 h-5" />
      </RouterLink>
      
      <div>
        <h1 class="text-2xl font-bold text-text-primary truncate">
          {{ video.title || video.filename }}
        </h1>
        <p class="text-text-secondary">{{ formatDate(video.created_at) }}</p>
      </div>
    </div>
    
    <!-- Video Preview and File Info -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Video Player -->
      <div class="lg:col-span-2">
        <Card class="overflow-hidden">
          <video
            controls
            class="w-full max-h-[480px] bg-black"
            :src="streamUrl"
          >
            Your browser does not support the video tag.
          </video>
        </Card>
      </div>
      
      <!-- File Information -->
      <Card class="p-4 space-y-3">
        <h2 class="text-lg font-semibold text-text-primary mb-4">File Information</h2>
        
        <div class="flex justify-between text-sm">
          <span class="text-text-secondary">Filename:</span>
          <span class="font-medium text-text-primary text-right break-all max-w-[180px]">{{ video.filename }}</span>
        </div>
        
        <div class="flex justify-between text-sm">
          <span class="text-text-secondary">Size:</span>
          <span class="font-medium text-text-primary">{{ formatFileSize(video.size_bytes) }}</span>
        </div>
        
        <div class="flex justify-between text-sm">
          <span class="text-text-secondary">Created:</span>
          <span class="font-medium text-text-primary">{{ formatDateTime(video.created_at) }}</span>
        </div>
        
        <div class="flex justify-between text-sm">
          <span class="text-text-secondary">Duration:</span>
          <span class="font-medium text-text-primary">{{ video.duration_seconds.toFixed(1) }}s</span>
        </div>
        
        <div class="flex justify-between text-sm">
          <span class="text-text-secondary">Resolution:</span>
          <span class="font-medium text-text-primary">{{ video.width }}x{{ video.height }}</span>
        </div>
        
        <div class="flex justify-between text-sm">
          <span class="text-text-secondary">Printer:</span>
          <span class="font-medium text-text-primary">{{ video.printer?.name || 'Unknown' }}</span>
        </div>
        
        <div class="flex justify-between text-sm items-center">
          <span class="text-text-secondary">Metadata:</span>
          <Badge
            :variant="video.metadata_status === 'complete' ? 'success' : 'warning'"
            :dot="true"
          >
            {{ video.metadata_status }}
          </Badge>
        </div>
        
        <div class="pt-2">
          <a
            :href="streamUrl"
            target="_blank"
            class="flex items-center justify-center gap-2 w-full px-4 py-2 bg-surface-elevated hover:bg-surface text-text-primary rounded-lg transition-colors text-sm"
          >
            <ExternalLink class="w-4 h-4" />
            Open Video Stream
          </a>
        </div>
      </Card>
    </div>
    
    <!-- Metadata & Processing Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Metadata Editor -->
      <Card class="p-4">
        <h2 class="text-lg font-semibold text-text-primary mb-4">Metadata Editor</h2>
        
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">
              Title <span class="text-error">*</span>
            </label>
            <input
              v-model="metadataForm.title"
              type="text"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
              placeholder="Enter video title"
              :class="{ 'border-error': metadataErrors.title }"
            />
            <p v-if="metadataErrors.title" class="text-error text-xs mt-1">Title is required</p>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Description</label>
            <textarea
              v-model="metadataForm.description"
              rows="3"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary resize-none"
              placeholder="Enter video description"
            />
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Tags</label>
            <input
              v-model="tagsInput"
              type="text"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
              placeholder="tag1, tag2, tag3"
              @input="updateTagsChips"
            />
            <div v-if="tagsChips.length > 0" class="flex flex-wrap gap-2 mt-2">
              <span
                v-for="tag in tagsChips"
                :key="tag"
                class="inline-flex items-center gap-1 px-2 py-1 bg-primary/15 text-primary rounded text-xs font-medium"
              >
                {{ tag }}
              </span>
            </div>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Category</label>
            <select
              v-model="metadataForm.category"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
            >
              <option value="">-- Select Category --</option>
              <option value="Film & Animation">Film & Animation</option>
              <option value="Autos & Vehicles">Autos & Vehicles</option>
              <option value="Music">Music</option>
              <option value="Pets & Animals">Pets & Animals</option>
              <option value="Sports">Sports</option>
              <option value="Travel & Events">Travel & Events</option>
              <option value="Gaming">Gaming</option>
              <option value="People & Blogs">People & Blogs</option>
              <option value="Comedy">Comedy</option>
              <option value="Entertainment">Entertainment</option>
              <option value="News & Politics">News & Politics</option>
              <option value="Howto & Style">Howto & Style</option>
              <option value="Education">Education</option>
              <option value="Science & Technology">Science & Technology</option>
              <option value="Nonprofits & Activism">Nonprofits & Activism</option>
            </select>
          </div>
          
          <Button variant="primary" class="w-full" :loading="savingMetadata" @click="saveMetadata">
            Save Metadata
          </Button>
          
          <div v-if="metadataStatus" class="mt-2">
            <div
              :class="[
                'px-3 py-2 rounded-lg text-sm',
                metadataStatus.type === 'success' ? 'bg-success/10 text-success' :
                metadataStatus.type === 'error' ? 'bg-error/10 text-error' :
                'bg-primary/10 text-primary'
              ]"
            >
              {{ metadataStatus.message }}
            </div>
          </div>
        </div>
      </Card>
      
      <!-- Processing Options -->
      <Card class="p-4">
        <h2 class="text-lg font-semibold text-text-primary mb-4">Processing Options</h2>
        
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">
              Zoom Level: <span class="text-primary font-semibold">{{ zoomLabel }}</span>
            </label>
            <select
              v-model="processingForm.zoom_level"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
            >
              <option value="-1">Fit Center (Letterbox)</option>
              <option value="0.1">Zoom Out (0.1x)</option>
              <option value="0.25">Zoom Out (0.25x)</option>
              <option value="0.5">Zoom Out (0.5x)</option>
              <option value="0.75">Zoom Out (0.75x)</option>
              <option value="0">No Zoom (0)</option>
              <option value="1">Standard (1.0x)</option>
              <option value="1.5">Zoom In (1.5x)</option>
              <option value="2">Zoom In More (2.0x)</option>
              <option value="3">Max Zoom (3.0x)</option>
            </select>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Target Duration (max 60s for Shorts)</label>
            <input
              v-model.number="processingForm.duration"
              type="number"
              min="1"
              max="60"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
            />
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Speed Factor (0.5x - 4x)</label>
            <input
              v-model.number="processingForm.speed_factor"
              type="number"
              min="0.5"
              max="4"
              step="0.1"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
            />
          </div>
          
          <!-- Text Overlay -->
          <div class="border border-border rounded-lg p-4 space-y-3">
            <h3 class="text-sm font-semibold text-text-primary">Text Overlay</h3>
            
            <div>
              <label class="block text-sm font-medium text-text-secondary mb-1">Text Content</label>
              <input
                v-model="processingForm.text_overlay.text"
                type="text"
                class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                placeholder="Enter text to overlay on video"
              />
            </div>
            
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-text-secondary mb-1">Position X</label>
                <input
                  v-model="processingForm.text_overlay.position_x"
                  type="text"
                  class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                />
                <div class="flex gap-1 mt-1">
                  <button type="button" class="px-2 py-0.5 bg-surface-elevated hover:bg-surface rounded text-xs text-text-secondary" @click="processingForm.text_overlay.position_x = 'left'">Left</button>
                  <button type="button" class="px-2 py-0.5 bg-surface-elevated hover:bg-surface rounded text-xs text-text-secondary" @click="processingForm.text_overlay.position_x = 'center'">Center</button>
                  <button type="button" class="px-2 py-0.5 bg-surface-elevated hover:bg-surface rounded text-xs text-text-secondary" @click="processingForm.text_overlay.position_x = 'right'">Right</button>
                </div>
              </div>
              
              <div>
                <label class="block text-sm font-medium text-text-secondary mb-1">Position Y</label>
                <input
                  v-model="processingForm.text_overlay.position_y"
                  type="text"
                  class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
                />
                <div class="flex gap-1 mt-1">
                  <button type="button" class="px-2 py-0.5 bg-surface-elevated hover:bg-surface rounded text-xs text-text-secondary" @click="processingForm.text_overlay.position_y = 'top'">Top</button>
                  <button type="button" class="px-2 py-0.5 bg-surface-elevated hover:bg-surface rounded text-xs text-text-secondary" @click="processingForm.text_overlay.position_y = 'center'">Center</button>
                  <button type="button" class="px-2 py-0.5 bg-surface-elevated hover:bg-surface rounded text-xs text-text-secondary" @click="processingForm.text_overlay.position_y = 'bottom'">Bottom</button>
                </div>
              </div>
            </div>
            
            <div>
              <label class="block text-sm font-medium text-text-secondary mb-1">Text Alignment</label>
              <select
                v-model="processingForm.text_overlay.text_align"
                class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
              >
                <option value="center">Center</option>
                <option value="left">Left</option>
                <option value="right">Right</option>
              </select>
            </div>
            
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-text-secondary mb-1">
                  Font Size: <span class="text-primary font-semibold">{{ processingForm.text_overlay.font_size }}px</span>
                </label>
                <input
                  v-model.number="processingForm.text_overlay.font_size"
                  type="range"
                  min="12"
                  max="120"
                  class="w-full"
                />
              </div>
              
              <div>
                <label class="block text-sm font-medium text-text-secondary mb-1">Font Color</label>
                <div class="flex gap-2 items-center">
                  <input
                    v-model="processingForm.text_overlay.font_color"
                    type="color"
                    class="w-12 h-9 rounded border border-border cursor-pointer"
                  />
                  <input
                    v-model="processingForm.text_overlay.font_color"
                    type="text"
                    class="flex-1 px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary text-sm"
                  />
                </div>
              </div>
            </div>
            
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-text-secondary mb-1">Background Color</label>
                <div class="flex gap-2 items-center">
                  <input
                    v-model="processingForm.text_overlay.bg_color"
                    type="color"
                    class="w-12 h-9 rounded border border-border cursor-pointer"
                  />
                  <input
                    v-model="processingForm.text_overlay.bg_color"
                    type="text"
                    class="flex-1 px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary text-sm"
                  />
                </div>
              </div>
              
              <div>
                <label class="block text-sm font-medium text-text-secondary mb-1">
                  Bg Opacity: <span class="text-primary font-semibold">{{ processingForm.text_overlay.bg_opacity * 100 }}%</span>
                </label>
                <input
                  v-model.number="processingForm.text_overlay.bg_opacity"
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  class="w-full"
                />
              </div>
            </div>
            
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-sm font-medium text-text-secondary mb-1">
                  Border Width: <span class="text-primary font-semibold">{{ processingForm.text_overlay.border_width }}px</span>
                </label>
                <input
                  v-model.number="processingForm.text_overlay.border_width"
                  type="range"
                  min="0"
                  max="10"
                  class="w-full"
                />
              </div>
              
              <div>
                <label class="block text-sm font-medium text-text-secondary mb-1">Border Color</label>
                <div class="flex gap-2 items-center">
                  <input
                    v-model="processingForm.text_overlay.border_color"
                    type="color"
                    class="w-12 h-9 rounded border border-border cursor-pointer"
                  />
                  <input
                    v-model="processingForm.text_overlay.border_color"
                    type="text"
                    class="flex-1 px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary text-sm"
                  />
                </div>
              </div>
            </div>
            
            <!-- Live Preview -->
            <div class="p-3 bg-surface-elevated rounded-lg border border-border">
              <div class="text-xs text-text-secondary mb-2">Preview:</div>
              <div
                class="min-h-[60px] flex items-center justify-center rounded p-2 break-words"
                :style="{
                  fontSize: processingForm.text_overlay.font_size + 'px',
                  color: processingForm.text_overlay.font_color,
                  textAlign: processingForm.text_overlay.text_align,
                  backgroundColor: hexToRgba(processingForm.text_overlay.bg_color, processingForm.text_overlay.bg_opacity),
                  border: processingForm.text_overlay.border_width > 0 ? `${processingForm.text_overlay.border_width}px solid ${processingForm.text_overlay.border_color}` : 'none'
                }"
              >
                {{ processingForm.text_overlay.text || 'Sample Text' }}
              </div>
            </div>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Background Music</label>
            <select
              v-model="processingForm.audio_track_id"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
            >
              <option :value="null">-- No Music --</option>
              <option v-for="track in audioTracks" :key="track.id" :value="track.id">{{ track.name }}</option>
            </select>
          </div>
          
          <div v-if="processingForm.audio_track_id" class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-sm font-medium text-text-secondary mb-1">
                Music Volume: <span class="text-primary font-semibold">{{ Math.round(processingForm.audio_volume * 100) }}%</span>
              </label>
              <input
                v-model.number="processingForm.audio_volume"
                type="range"
                min="0"
                max="1"
                step="0.01"
                class="w-full"
              />
            </div>
          </div>
          
          <div>
            <label class="block text-sm font-medium text-text-secondary mb-1">Crop Mode</label>
            <select
              v-model="processingForm.crop_mode"
              class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
            >
              <option value="center">Center</option>
              <option value="left">Left</option>
              <option value="right">Right</option>
            </select>
          </div>
          
          <Button
            variant="primary"
            class="w-full"
            :loading="processing"
            @click="processVideo"
          >
            <Wand2 class="w-4 h-4" />
            Process Video
          </Button>
          
          <div v-if="processingStatus" class="mt-2">
            <div
              :class="[
                'px-3 py-2 rounded-lg text-sm',
                processingStatus.type === 'success' ? 'bg-success/10 text-success' :
                processingStatus.type === 'error' ? 'bg-error/10 text-error' :
                'bg-primary/10 text-primary'
              ]"
            >
              {{ processingStatus.message }}
            </div>
          </div>
        </div>
      </Card>
    </div>
    
    <!-- Upload Status -->
    <Card class="p-4">
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-lg font-semibold text-text-primary">Upload Status</h2>
        <div
          v-if="video.metadata_status !== 'complete'"
          class="flex items-center gap-2 text-warning text-sm"
        >
          <AlertTriangle class="w-4 h-4" />
          <span>Complete metadata before uploading</span>
        </div>
      </div>
      
      <div v-if="videoUploads.length > 0" class="space-y-3">
        <div
          v-for="upload in videoUploads"
          :key="upload.id"
          class="flex flex-col p-3 bg-surface-elevated border border-border rounded-lg"
        >
          <div class="flex items-center gap-3">
            <span class="text-lg">{{ upload.platform === 'youtube' ? '▶️' : '🎵' }}</span>
            <div class="flex-1">
              <div class="flex items-center gap-2">
                <span class="font-medium text-sm text-text-primary">{{ upload.title || 'Untitled' }}</span>
                <Badge
                  :variant="upload.status === 'completed' ? 'success' : upload.status === 'failed' ? 'error' : upload.status === 'uploading' ? 'info' : 'warning'"
                  size="sm"
                >
                  {{ upload.status }}
                </Badge>
                <a
                  v-if="upload.status === 'completed' && upload.upload_url"
                  :href="upload.upload_url"
                  target="_blank"
                  class="text-primary text-xs hover:underline ml-auto"
                >
                  View →
                </a>
              </div>
              <div class="text-text-secondary text-xs mt-0.5">
                {{ upload.platform }} · {{ upload.uploaded_at ? formatDateTime(upload.uploaded_at) : 'Pending' }}
              </div>
            </div>
          </div>
          
          <!-- Progress bar for uploading -->
          <div v-if="upload.status === 'uploading' && upload.upload_progress" class="w-full h-1 bg-border rounded-full mt-2 overflow-hidden">
            <div
              class="h-full bg-primary transition-all duration-300"
              :style="{ width: upload.upload_progress + '%' }"
            />
          </div>
          
          <!-- Error message -->
          <div v-if="upload.status === 'failed' && upload.error_message" class="text-error text-xs mt-2">
            {{ upload.error_message }}
          </div>
        </div>
      </div>
      
      <div v-else class="text-center py-8">
        <Upload class="w-12 h-12 text-text-muted mx-auto mb-3" />
        <p class="text-text-secondary">No uploads yet. Process a video and upload it to a platform.</p>
      </div>
      
      <div class="flex gap-3 mt-4">
        <Button
          variant="primary"
          class="flex-1"
          :disabled="video.metadata_status !== 'complete' || processedVideos.length === 0"
          @click="uploadToYouTube"
        >
          <Upload class="w-4 h-4" />
          Upload to YouTube
        </Button>
        <Button
          variant="secondary"
          class="flex-1"
          :disabled="video.metadata_status !== 'complete' || processedVideos.length === 0"
          @click="showTiktokModal = true"
        >
          <Music2 class="w-4 h-4" />
          Upload to TikTok
        </Button>
      </div>
    </Card>
    
    <!-- Processed Versions -->
    <Card class="p-4">
      <h2 class="text-lg font-semibold text-text-primary mb-4">Processed Versions</h2>
      
      <div v-if="processedVideos.length > 0" class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-border">
              <th class="text-left text-sm font-medium text-text-secondary py-2 px-2">Preview</th>
              <th class="text-left text-sm font-medium text-text-secondary py-2 px-2">Format</th>
              <th class="text-left text-sm font-medium text-text-secondary py-2 px-2">Resolution</th>
              <th class="text-left text-sm font-medium text-text-secondary py-2 px-2">Duration</th>
              <th class="text-left text-sm font-medium text-text-secondary py-2 px-2">Status</th>
              <th class="text-left text-sm font-medium text-text-secondary py-2 px-2">Uploads</th>
              <th class="text-left text-sm font-medium text-text-secondary py-2 px-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="pv in processedVideos"
              :key="pv.id"
              class="border-b border-border/50 hover:bg-surface-elevated/50"
            >
              <td class="py-2 px-2">
                <button
                  v-if="pv.status === 'completed'"
                  class="p-1.5 rounded-lg bg-surface-elevated hover:bg-primary/10 transition-colors"
                  @click="previewProcessed(pv)"
                >
                  <Play class="w-4 h-4 text-text-primary" />
                </button>
                <span v-else class="text-text-muted text-lg opacity-30">▶️</span>
              </td>
              <td class="py-2 px-2 text-sm text-text-primary">{{ pv.format.toUpperCase() }}</td>
              <td class="py-2 px-2 text-sm text-text-primary">{{ pv.width }}x{{ pv.height }}</td>
              <td class="py-2 px-2 text-sm text-text-primary">{{ Math.round(pv.duration_seconds) }}s</td>
              <td class="py-2 px-2">
                <Badge
                  :variant="pv.status === 'completed' ? 'success' : pv.status === 'failed' ? 'error' : 'warning'"
                  size="sm"
                >
                  {{ pv.status }}
                </Badge>
              </td>
              <td class="py-2 px-2">
                <div class="flex flex-wrap gap-1">
                  <Badge
                    v-for="u in getUploadsForProcessed(pv.id)"
                    :key="u.id"
                    :variant="u.status === 'completed' ? 'success' : u.status === 'failed' ? 'error' : u.status === 'uploading' ? 'info' : 'warning'"
                    size="sm"
                  >
                    {{ u.platform }}: {{ u.status }}
                  </Badge>
                  <span v-if="getUploadsForProcessed(pv.id).length === 0" class="text-text-secondary text-xs">None</span>
                </div>
              </td>
              <td class="py-2 px-2">
                <div v-if="pv.status === 'completed'" class="flex gap-1">
                  <a
                    :href="getProcessedUrl(pv)"
                    download
                    class="p-1.5 rounded-lg bg-surface-elevated hover:bg-success/10 text-text-muted hover:text-success transition-colors"
                    title="Download"
                  >
                    <Download class="w-4 h-4" />
                  </a>
                  <button
                    class="p-1.5 rounded-lg bg-surface-elevated hover:bg-primary/10 text-text-muted hover:text-primary transition-colors"
                    title="Upload to YouTube"
                    @click="uploadProcessedToYouTube(pv.id)"
                  >
                    <Upload class="w-4 h-4" />
                  </button>
                  <button
                    class="p-1.5 rounded-lg bg-surface-elevated hover:bg-secondary/10 text-text-muted hover:text-secondary transition-colors"
                    title="Upload to TikTok"
                    @click="openTiktokModal(pv.id)"
                  >
                    <Music2 class="w-4 h-4" />
                  </button>
                  <button
                    class="p-1.5 rounded-lg bg-surface-elevated hover:bg-error/10 text-text-muted hover:text-error transition-colors"
                    title="Delete"
                    @click="deleteProcessedVideo(pv.id)"
                  >
                    <Trash2 class="w-4 h-4" />
                  </button>
                </div>
                <span v-else class="text-text-secondary text-xs">Processing...</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <div v-else class="text-center py-8">
        <p class="text-text-secondary">No processed versions yet. Use the Processing Options panel above.</p>
      </div>
    </Card>
    
    <!-- TikTok Upload Modal -->
    <Modal
      v-model="showTiktokModal"
      title="Upload to TikTok"
      size="md"
    >
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-text-secondary mb-1">Privacy</label>
          <select
            v-model="tiktokForm.privacy_status"
            class="w-full px-3 py-2 bg-surface-elevated border border-border rounded-lg text-text-primary focus:outline-none focus:border-primary"
            disabled
          >
            <option value="private">Private Only</option>
          </select>
          <p class="text-warning text-xs mt-1">
            Your TikTok app is in sandbox mode. Only private uploads are allowed.
          </p>
        </div>
        
        <div class="space-y-2">
          <label class="flex items-center gap-2 cursor-pointer text-sm text-text-primary">
            <input v-model="tiktokForm.draft" type="checkbox" class="w-4 h-4 rounded border-border" />
            <span>Upload as Draft <span class="text-text-secondary text-xs">(Recommended - allows editing before publishing)</span></span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer text-sm text-text-primary">
            <input v-model="tiktokForm.allow_comments" type="checkbox" class="w-4 h-4 rounded border-border" />
            <span>Allow Comments</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer text-sm text-text-primary">
            <input v-model="tiktokForm.allow_duet" type="checkbox" class="w-4 h-4 rounded border-border" />
            <span>Allow Duet</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer text-sm text-text-primary">
            <input v-model="tiktokForm.allow_stitch" type="checkbox" class="w-4 h-4 rounded border-border" />
            <span>Allow Stitch</span>
          </label>
        </div>
        
        <div class="bg-surface-elevated p-3 rounded-lg text-sm text-text-secondary">
          <strong class="text-text-primary">Note:</strong> 
          <span v-if="tiktokForm.draft">Draft uploads go to your TikTok inbox for editing before publishing.</span>
          <span v-else>Direct publish will post the video immediately without editing.</span>
          Check the Uploads page for status.
        </div>
        
        <div class="flex gap-3">
          <Button variant="secondary" class="flex-1" @click="showTiktokModal = false">
            Cancel
          </Button>
          <Button variant="primary" class="flex-1" :loading="uploadingTiktok" @click="confirmTiktokUpload">
            Upload
          </Button>
        </div>
      </div>
    </Modal>
    
    <!-- Video Preview Modal -->
    <Modal
      v-model="showPreviewModal"
      title="Preview"
      size="lg"
    >
      <div class="space-y-4">
        <video
          v-if="previewVideoUrl"
          controls
          class="w-full max-h-[70vh] rounded-lg bg-black"
          :src="previewVideoUrl"
          autoplay
        />
        <p class="text-center text-text-secondary text-sm">
          {{ previewVideoInfo }}
        </p>
      </div>
    </Modal>
  </div>
  
  <!-- Loading state -->
  <div v-else class="flex items-center justify-center h-64">
    <Loader2 class="w-8 h-8 text-primary animate-spin" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  ArrowLeft,
  Wand2,
  Upload,
  Download,
  Music2,
  Play,
  Loader2,
  Trash2,
  ExternalLink,
  AlertTriangle
} from 'lucide-vue-next'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Badge from '@/components/ui/Badge.vue'
import Modal from '@/components/ui/Modal.vue'
import api from '@/composables/useApi'

const route = useRoute()

const streamUrl = computed(() => {
  if (!video.value) return ''
  const token = localStorage.getItem('access_token') || ''
  const baseUrl = api.defaults.baseURL || '/api'
  return `${baseUrl}/videos/${video.value.id}/stream?token=${token}`
})

const video = ref<any>(null)
const processedVideos = ref<any[]>([])
const videoUploads = ref<any[]>([])
const audioTracks = ref<any[]>([])
const loading = ref(false)
const savingMetadata = ref(false)
const processing = ref(false)
const uploadingTiktok = ref(false)

const metadataForm = ref({
  title: '',
  description: '',
  category: ''
})
const tagsInput = ref('')
const tagsChips = ref<string[]>([])
const metadataErrors = ref({ title: false })
const metadataStatus = ref<{ type: string; message: string } | null>(null)

const processingForm = ref({
  zoom_level: 0.1,
  duration: 60,
  speed_factor: 1,
  crop_mode: 'center',
  audio_track_id: null as number | null,
  audio_volume: 0.5,
  text_overlay: {
    text: '',
    position_x: 'center',
    position_y: 'bottom',
    text_align: 'center',
    font_size: 36,
    font_color: '#ffffff',
    bg_color: '#000000',
    bg_opacity: 0.5,
    border_width: 0,
    border_color: '#000000'
  }
})
const processingStatus = ref<{ type: string; message: string } | null>(null)

const showTiktokModal = ref(false)
const tiktokForm = ref({
  privacy_status: 'private',
  allow_comments: true,
  allow_duet: true,
  allow_stitch: true,
  draft: true
})
const selectedProcessedId = ref<number | null>(null)

const showPreviewModal = ref(false)
const previewVideoUrl = ref('')
const previewVideoInfo = ref('')

const zoomLabel = computed(() => {
  const labels: Record<string, string> = {
    '-1': 'Fit Center (Letterbox)',
    '0.1': 'Zoom Out (0.1x)',
    '0.25': 'Zoom Out (0.25x)',
    '0.5': 'Zoom Out (0.5x)',
    '0.75': 'Zoom Out (0.75x)',
    '0': 'No Zoom (0)',
    '1': 'Standard (1.0x)',
    '1.5': 'Zoom In (1.5x)',
    '2': 'Zoom In More (2.0x)',
    '3': 'Max Zoom (3.0x)'
  }
  return labels[String(processingForm.value.zoom_level)] || processingForm.value.zoom_level + 'x'
})

const loadVideo = async () => {
  loading.value = true
  try {
    const id = parseInt(route.params.id as string)
    const response = await api.get(`/videos/${id}`)
    video.value = response.data
    
    // Initialize forms
    metadataForm.value = {
      title: response.data.title || '',
      description: response.data.description || '',
      category: response.data.category || ''
    }
    
    // Set tags
    const tags = response.data.tags?.tags || []
    tagsInput.value = tags.join(', ')
    tagsChips.value = tags
    
    // Set processed videos and uploads
    processedVideos.value = response.data.processed_videos || []
    videoUploads.value = response.data.uploads || []
  } catch (err) {
    console.error('Failed to load video:', err)
  } finally {
    loading.value = false
  }
}

const loadAudioTracks = async () => {
  try {
    const response = await api.get('/audio')
    audioTracks.value = response.data
  } catch (err) {
    console.error('Failed to load audio tracks:', err)
  }
}

const updateTagsChips = () => {
  tagsChips.value = tagsInput.value
    .split(',')
    .map(t => t.trim())
    .filter(t => t.length > 0)
}

const saveMetadata = async () => {
  metadataErrors.value.title = !metadataForm.value.title.trim()
  if (metadataErrors.value.title) return
  
  savingMetadata.value = true
  metadataStatus.value = { type: 'info', message: 'Saving metadata...' }
  
  try {
    const id = parseInt(route.params.id as string)
    const response = await api.put(`/videos/${id}/metadata`, {
      title: metadataForm.value.title.trim(),
      description: metadataForm.value.description.trim(),
      tags: tagsChips.value,
      category: metadataForm.value.category
    })
    
    video.value = { ...video.value, ...response.data }
    metadataStatus.value = { type: 'success', message: 'Metadata saved successfully!' }
    setTimeout(() => { metadataStatus.value = null }, 3000)
  } catch (err: any) {
    metadataStatus.value = { type: 'error', message: err.response?.data?.detail || 'Failed to save metadata' }
  } finally {
    savingMetadata.value = false
  }
}

const processVideo = async () => {
  processing.value = true
  processingStatus.value = { type: 'info', message: 'Processing video... This may take a few minutes.' }
  
  try {
    const id = parseInt(route.params.id as string)
    const payload: any = {
      platform: 'shorts',
      zoom_level: processingForm.value.zoom_level,
      duration: processingForm.value.duration,
      speed_factor: processingForm.value.speed_factor,
      crop_mode: processingForm.value.crop_mode,
      audio_track_id: processingForm.value.audio_track_id,
      audio_volume: processingForm.value.audio_volume
    }
    
    if (processingForm.value.text_overlay.text) {
      payload.text_overlay = processingForm.value.text_overlay
    }
    
    const response = await api.post(`/videos/${id}/process`, payload)
    
    processingStatus.value = { type: 'success', message: 'Processing completed! Video is ready to upload.' }
    processedVideos.value.push(response.data)
    setTimeout(() => { processingStatus.value = null }, 3000)
  } catch (err: any) {
    processingStatus.value = { type: 'error', message: err.response?.data?.detail || 'Processing failed' }
  } finally {
    processing.value = false
  }
}

const getUploadsForProcessed = (processedId: number) => {
  return videoUploads.value.filter(u => u.processed_video_id === processedId)
}

const getProcessedUrl = (pv: any) => {
  if (!pv.processed_path) return ''
  const filename = pv.processed_path.split('/').pop()
  return `/processed/${filename}`
}

const previewProcessed = (pv: any) => {
  previewVideoUrl.value = getProcessedUrl(pv)
  previewVideoInfo.value = `${pv.width}x${pv.height} · ${Math.round(pv.duration_seconds)}s`
  showPreviewModal.value = true
}

const deleteProcessedVideo = async (processedId: number) => {
  if (!confirm('Are you sure you want to delete this processed version?')) return
  
  try {
    const id = parseInt(route.params.id as string)
    await api.delete(`/videos/${id}/processed/${processedId}`)
    processedVideos.value = processedVideos.value.filter(pv => pv.id !== processedId)
  } catch (err: any) {
    alert(err.response?.data?.detail || 'Failed to delete processed video')
  }
}

const uploadToYouTube = () => {
  const latestProcessed = processedVideos.value
    .filter(pv => pv.status === 'completed')
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0]
  
  if (latestProcessed) {
    uploadProcessedToYouTube(latestProcessed.id)
  }
}

const uploadProcessedToYouTube = async (processedId: number) => {
  try {
    await api.post(`/uploads/youtube/${processedId}`, {
      title: video.value?.title || video.value?.filename,
      description: video.value?.description || '',
      tags: tagsChips.value
    })
    
    // Refresh uploads
    await loadVideo()
  } catch (err: any) {
    alert(err.response?.data?.detail || 'Failed to upload to YouTube')
  }
}

const openTiktokModal = (processedId: number) => {
  selectedProcessedId.value = processedId
  showTiktokModal.value = true
}

const confirmTiktokUpload = async () => {
  if (!selectedProcessedId.value) return
  
  uploadingTiktok.value = true
  try {
    await api.post(`/uploads/tiktok/${selectedProcessedId.value}`, {
      title: video.value?.title || video.value?.filename,
      description: video.value?.description || '',
      tags: tagsChips.value,
      privacy_status: tiktokForm.value.privacy_status,
      allow_comments: tiktokForm.value.allow_comments,
      allow_duet: tiktokForm.value.allow_duet,
      allow_stitch: tiktokForm.value.allow_stitch,
      draft: tiktokForm.value.draft
    })
    
    showTiktokModal.value = false
    await loadVideo()
  } catch (err: any) {
    alert(err.response?.data?.detail || 'Failed to upload to TikTok')
  } finally {
    uploadingTiktok.value = false
  }
}

function formatFileSize(bytes: number): string {
  const sizes = ['B', 'KB', 'MB', 'GB']
  if (bytes === 0) return '0 B'
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric'
  })
}

function formatDateTime(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function hexToRgba(hex: string, opacity: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${opacity})`
}

watch(tagsInput, updateTagsChips)

onMounted(() => {
  loadVideo()
  loadAudioTracks()
})
</script>